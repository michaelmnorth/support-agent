# Scheduling assistant: plan, pushback, and limits

Written 2026-10-30 against current Anthropic and Microsoft documentation. Facts marked **[doc]** come from
official pages; **[verify]** means the docs do not say and you must test it once in the work tenant.

## 1. What you asked for, line by line

| You want | Verdict | How, and the catch |
|----------|---------|--------------------|
| Look at my Outlook calendar and blocked time | **Yes** | Microsoft 365 connector reads calendar events **[doc]**. The tool takes those events as input. |
| Never schedule within 30 min of any meeting, either side | **Yes, in code** | `scheduler/availability.py`, 37 tests. Also: working hours, lunch block, 24h lead time, PTO dates, client's own hours. The model is told never to do this math itself. |
| Draft the reply in my format, in Outlook | **Yes, once write is on** | Connector write actions include "manage drafts" and "send mail" **[doc]**, but an org Owner must enable write actions and an Entra Global Admin must consent once **[doc]**. Until then: the assistant hands you the text. |
| Send automatically or by one click | **Yes, per client** | `automation: draft_only / ask_then_send / auto_send` on each client profile. Start every client at `ask_then_send`. |
| Reply in Slack as me | **No, not with the Slack connector** | The claude.ai Slack connector is documented as *search only* **[doc]**. Nothing posts. Three ways out, in §4. |
| Create the Teams invite when the client says yes | **Yes, probably** | Connector write includes "create calendar events" **[doc]**. The tool returns a Graph event payload with `isOnlineMeeting: true, onlineMeetingProvider: teamsForBusiness`. Whether the connector passes those two fields through is **[verify]**. The direct Graph provider does it for certain. |
| Default to Eastern, override per client, convert | **Yes, in code** | Client profiles carry an IANA zone; output always shows both zones; DST and half-hour zones tested. |
| Triggered when an email or Slack message arrives | **No native trigger for email or Teams.** Slack: yes via Claude Tag only. | Claude Code scheduled tasks trigger on schedule, HTTP, or GitHub events only **[doc]**. So: a scheduled sweep every 15 to 30 minutes, or Power Automate calling the routine's HTTP trigger. Details in §3. |
| Fully automatic end to end | **Possible, but do not start there** | Everything after the first approval can be automatic. Sending the first proposal to a human you have never emailed is where mistakes cost you. |
| Repeatable, pluggable, roll out to the team | **Yes** | This folder *is* a Claude plugin (skill + MCP server). Org admins upload it under Organization settings > Plugins & skills and can make it "Installed by default" **[doc]**. Each person connects their own M365 account. |

## 2. Shape of the system

```
 inbound                    reasoning (Claude)                 deterministic core (this repo)          outbound
 ───────                    ──────────────────                 ──────────────────────────────          ────────
 Outlook email  ─┐   read via M365 connector ──►  extract request  ──►  propose_times(busy, client) ──►  draft reply
 Slack DM/chan  ─┼─► read via Slack connector      who / how long /     check_time(start)                 Outlook draft or send
 Teams chat     ─┘   read via M365 connector       constraints          confirm_meeting(...) ──► Graph    Teams invite (M365 connector
                                                                        event payload                      or Graph provider)
 clients/<name>/client.yaml  ──►  time zone, contacts, duration, automation level, notes
 preferences.yaml            ──►  your hours, buffer, lead time, lunch, voice
```

The split matters: Claude is good at reading "any chance you have 30 min late next week, I'm in Denver" and bad
at arithmetic across DST boundaries. Code is the opposite. So the model only ever *passes data* to the tools
and *copies* formatted time lines back out. The tests are the contract.

Three ways the core can be reached, same code:

| Surface | How the tools are called | When |
|---------|--------------------------|------|
| Claude Code / Claude Desktop / Cowork | MCP server (`.mcp.json`, stdio) | Day-to-day use on your machine |
| Claude Code cloud scheduled task, Cowork task | `python -m scheduler.cli ...` from the skill (scripts run in the sandbox) | Scheduled sweeps |
| Local Python agent (Agent SDK) | Import `scheduler.service` directly | "Runs on my computer" with no connector |

## 3. The trigger problem, honestly

Nothing in Claude fires on "new email arrived" **[doc]**. Your real choices:

**A. Scheduled sweep (recommended first).** A Claude Code cloud scheduled task or Cowork scheduled task every
15 minutes, weekdays, with your M365 connector attached. Prompt is in
`skills/scheduling-assistant/references/inbox-sweep.md`. Latency: up to 15 minutes. Cost: one short run per
sweep even when there is nothing to do. Ownership: the task is yours, not the team's; each teammate makes
their own **[doc]**.

**B. Event-driven via Power Automate.** "When a new email arrives (V3)" in Power Automate (included with M365)
→ HTTP action → `POST .../routines/{id}/fire` with the email id in the body **[doc]**. Near-instant. Catches:
the HTTP action is a Premium connector (per-user license) **[doc, via training module]**, the routine token must
be stored in the flow, and the flow is per-mailbox. Good second step once A proves the logic.

**C. Slack in real time: Claude Tag.** It answers DMs and @mentions immediately and can use your personal
connectors (your calendar, your mail) in DMs with your approval **[doc]**. But it speaks as "Claude", not as
you, so it suits a `#scheduling` channel where clients know they are talking to an assistant, not a DM you
want to look like you typed it. Whether the M365 connector specifically is available to Claude Tag is
**[verify]**: the connector guides list Google Calendar/Gmail, not M365.

**D. Fully local daemon.** Windows Task Scheduler every 5 minutes runs a Python script using the Agent SDK
plus `providers/graph.py` (MSAL sign-in, your own Entra app registration). No connector, no admin toggle for
write actions, instant control. Catches: an Entra app registration (your tenant may require an admin), the
machine must be on, and it uses an API key rather than your Claude seat. Skeleton in `local_agent/`.

## 4. Slack, specifically

| Option | Posts as | Reads DMs between you and a client | Needs |
|--------|----------|-----------------------------------|-------|
| Slack connector (what you have) | nobody, read-only | yes (search) | nothing |
| You paste the draft | you | n/a | nothing |
| Claude Tag | "Claude" | only DMs *with Claude*, or channels it is in | Team/Enterprise, Slack admin installs app, Owner pairs workspace |
| Custom Slack app, your user token | you | yes, and gets `message.im` events over Socket Mode (no public URL) | Slack admin approval in Enterprise Grid, a process to run it |

Recommendation: read from Slack with the connector, reply by pasting for now, and move client scheduling
conversations toward email where the loop can close automatically. If Slack must be first class, the custom
user-token app is the only way to post as you and get real-time events.

## 5. Safety rails built in

- **Approval gate per client** (`automation`). New or unknown contacts are always ask-first.
- **Validation before confirmation**: `check_time` runs against the fresh calendar, never the model's memory.
- **Idempotent invites**: `transactionId` on every event payload; the skill searches for an existing event
  with the same attendee in the same hour before creating one.
- **Processed marker**: Outlook category `Scheduled by assistant` plus `clients/<id>/scheduling-log.md`.
- **No guessing zones**: unknown requester zone produces a warning and an explicit sentence in the draft.
- **Lead time**: nothing is offered sooner than 24 hours out (configurable), so an automated reply never books
  you for "in 40 minutes".
- **Tentative counts as busy** by default. You chose a 30-minute buffer; the same logic applies around
  tentative holds unless you flip `treat_tentative_as_busy`.

## 6. Things that will bite, and what I did about them

1. **"Next Tuesday" is ambiguous on a Friday.** The skill asks a one-line question when a reply is ambiguous
   rather than booking. Keep it that way.
2. **Clients who propose a time in *your* zone by mistake.** `check_time` output carries both zones; the
   confirmation shows both, so a mix-up is visible before the invite goes out.
3. **Recurring meetings.** The tool expects an *expanded* view (every occurrence as its own item). Graph's
   calendarView does this; if the connector returns series masters only, the sweep will think you are free.
   **[verify]** on day one by comparing a week of connector output to Outlook.
4. **All-day events.** `showAs: free` all-day reminders are ignored; `oof`/`busy` all-day blocks the day.
5. **Private events**: times are used, subjects are not needed.
6. **Connector returns times without offsets**: the tool reads the `timeZone` field on each item; if that is
   missing, it assumes UTC and warns.
7. **The model rewriting time lines "for tone"**: the skill forbids it and templates separate prose from the
   `{options}` block.
8. **Approval latency in sweep mode**: your "send" reply is seen on the *next* sweep. Fine at 15 minutes; if
   not, say "send the Acme draft" in an interactive session.

## 7. Rolling it out to the team (Claude Enterprise)

What an **Owner/admin** does once:
1. Organization settings > Connectors: add Microsoft 365, enable write actions (mail, calendar). An Entra
   Global Admin accepts the consent link **[doc]**.
2. Organization settings > Plugins & skills: upload this folder as a plugin zip (or sync from a GitHub repo),
   set availability to "Available to install" for a pilot group, later "Installed by default" **[doc]**.
   Enterprise can scope by SCIM group **[doc]**.
3. (Claude Code CLI users) managed settings: `enabledPlugins` and `extraKnownMarketplaces` push it to every
   machine **[doc]**.

What **each teammate** does:
1. Connect their own M365 account to the connector.
2. Copy `preferences.yaml` and fill in hours, zone, sign-off. Create `clients/` for their accounts (or point
   `SCHEDULER_CLIENTS_DIR` at their existing client folders).
3. Create their own scheduled sweep task if they want sweep mode (tasks are per user **[doc]**).

What stays shared: the skill, the templates' structure, the tool code. What stays personal: hours, voice,
clients, connectors, scheduled tasks.

## 8. Phased plan

| Phase | Scope | Exit criterion |
|-------|-------|----------------|
| 0 (this repo) | Core logic, CLI, MCP server, skill, docs. Mock calendar. | Tests green. Demo runs. |
| 1 (your work instance, 1 week) | Interactive only: "handle the scheduling email from Jane". Connector read, drafts via connector if write is on. `ask_then_send` everywhere. | 10 real threads handled with zero wrong times. |
| 2 (2 weeks) | Scheduled sweep every 15 min. Still ask-first. Log file populated. | Sweep catches every scheduling email you also noticed; no duplicates. |
| 3 | `auto_send` for 2 or 3 trusted clients. Invite creation automatic after a clear yes. | A full loop closes with no touch from you. |
| 4 | Team pilot with 3 colleagues via plugin upload. Collect their voice templates. | They stop asking you how it works. |
| 5 (optional) | Event-driven: Power Automate → routine fire. Custom Slack app if Slack stays important. | Latency under 2 minutes. |

## 9. Day-one verification checklist (work instance)

- [ ] Connector returns your calendar for the next 7 days with `showAs`, recurring meetings expanded.
- [ ] `propose_times` with that data matches what you would pick by eye (do this three times).
- [ ] Creating an event from `event_payload` yields a Teams link in the created event.
- [ ] A draft created in a thread appears in Outlook Drafts with the right recipients.
- [ ] Category `Scheduled by assistant` can be set on a message (if not, log-file fallback).
- [ ] One UK or India client profile: the proposal shows sensible local times for them.
