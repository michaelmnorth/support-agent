# Channel playbook: what each connector can do (checked against Anthropic docs, 2026-10-30)

## Microsoft 365 connector (Outlook mail + calendar, Teams)

Read (always on once connected): email threads, calendar events, Teams chats/channels, SharePoint/OneDrive.
Write (only after an org Owner turns on write actions and an Entra admin grants consent once): send mail,
manage drafts, create/update/delete calendar events, "find meeting times", send Teams chat/channel messages.

### Reading the calendar for the tools

Ask the connector for the owner's calendar events between `now` and `now + lookahead_days` (use the
calendar-view style query that expands recurring meetings). Keep these fields per event:
`subject, start, end, showAs, isAllDay, isCancelled`. Pass the list straight into `propose_times(busy=...)`.
Both Graph-shaped items (`{"start": {"dateTime", "timeZone"}}`) and flat items (`{"start": iso, "end": iso}`)
are accepted. Private events: keep them, you only need the times.

If the connector returns times without an offset, they are in the zone the connector reports; the tool
reads `timeZone` from each item. Never strip it.

### Drafting / sending email

- Prefer "reply in thread" so the client keeps context. Body = the tool's `draft` (plain text is fine).
- `draft_only` and `ask_then_send` before approval: create a draft in the thread, then tell the owner where it
  is. After approval: send the draft.
- Mark the inbound message with category `Scheduled by assistant` after you act.

### Creating the Teams invite

Create a calendar event with the `event_payload` from `confirm_meeting`: subject, start/end with
`timeZone`, attendees, `isOnlineMeeting: true`, `onlineMeetingProvider: teamsForBusiness`,
`allowNewTimeProposals: true`, `transactionId`. Outlook sends the invitations itself. Whether the connector
exposes `isOnlineMeeting` is **not documented**; test once. If the created event has no Teams link, tell the
owner plainly and leave the event in place for them to toggle Teams on.

### Teams chat

Sending a Teams chat message is a write action with its own per-tool admin restriction. If allowed, post the
`draft` to the client's chat. If not allowed, give the owner the text to paste.

## Slack connector (claude.ai)

Documented capability is **search only**: channels, DMs, files. There is no documented post/DM action. So:

- Reading a scheduling request from Slack: yes, search the channel or DM for the thread and extract it.
- Replying in Slack as the owner: **not possible through this connector.** Options, in order of effort:
  1. Give the owner the `draft` text to paste (default).
  2. Claude Tag (Claude in Slack, Team/Enterprise): responds in real time to DMs and @mentions and can post
     in channels and threads, but it posts **as "Claude"**, not as the owner, and uses either the admin-set
     agent identity or the member's own approved personal connectors. Good for a shared `#scheduling` channel
     where clients are told they are talking to an assistant.
  3. A custom Slack app with the owner's user token (`chat:write`, `im:history`) posts as the owner and can
     receive DM events (Socket Mode, no public URL). Needs Slack admin approval in Enterprise Grid and a
     process to run it. This is the "runs on my computer" path for Slack.

## Microsoft Graph directly (local path, no connector)

`providers/graph.py` implements calendarView, event creation with Teams, drafts, replies, and sendMail with
MSAL delegated sign-in. Requires an Entra app registration (delegated scopes `User.Read, Calendars.ReadWrite,
Mail.ReadWrite, Mail.Send, MailboxSettings.Read`; none of them need admin consent by Graph's definition, but
the tenant's user-consent policy may still require an admin to approve). Untested here: no tenant available.

## Triggers (how the assistant finds out something arrived)

| Event | Native Claude trigger? | What works instead |
|-------|------------------------|--------------------|
| New Outlook email | No | Scheduled sweep (Claude Code cloud scheduled task or Cowork scheduled task every 15 to 30 min with the M365 connector), or Power Automate -> Claude Code routine API trigger (needs a Premium HTTP action license) |
| New Slack DM / @mention | Yes, via Claude Tag only | Claude Tag handles the Slack side and can use the member's personal connectors in DMs |
| New Teams chat | No | Scheduled sweep reading Teams chats via the M365 connector, or Graph change notifications (needs a public HTTPS endpoint) |
| Client replies "yes" | No | Same sweep; the log file tells the sweep which threads are awaiting an answer |

Claude Code cloud scheduled tasks include the creator's claude.ai connectors by default, can perform writes,
and belong to the individual user (not shared with the team). Each teammate creates their own.
