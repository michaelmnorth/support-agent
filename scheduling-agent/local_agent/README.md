# Fully local path (Agent SDK)

For "runs on my computer with no connector": a Python script that Windows Task Scheduler runs every 5 minutes.
It signs into Microsoft Graph as you (MSAL, delegated), reads unread inbox mail, and runs a Claude Agent SDK
loop with the scheduler MCP server attached. **Not runnable here**: it needs an Entra app registration, the
`claude-agent-sdk` package, and an API key. It is a skeleton to start from, not a finished daemon.

```
pip install claude-agent-sdk msal requests
set ANTHROPIC_API_KEY=...
set GRAPH_CLIENT_ID=...        # Entra app registration, "Mobile and desktop", http://localhost, public client flows = Yes
set GRAPH_TENANT_ID=...
set SCHEDULER_PROVIDER=graph
python local_agent/run_once.py
```

What it does per run:
1. `GraphProvider.list_unread_since(minutes=30)` (to add; see note in `run_once.py`).
2. For each message, call `query()` with the SKILL.md as system prompt, the scheduler MCP server, and the
   message text; Claude decides request / reply / unrelated and calls `propose_times` / `confirm_meeting`.
3. `confirm_meeting(create=True)` goes through `providers/graph.py` and really creates the Teams event.
4. Drafts via `GraphProvider.create_draft(reply_to_message_id=...)`; sending only when the client profile
   says `auto_send` or the owner approved in the previous run.

Why you might not want this: it uses an API key (billed separately from your Claude seat), the laptop must be
on, and every write goes through *your* app registration rather than the org-sanctioned connector. Why you
might: zero admin toggles, sub-5-minute latency, and you own every line.

Schedule it:

```
schtasks /create /tn "SchedulingAssistant" /sc minute /mo 5 /tr "python C:\path\to\scheduling-agent\local_agent\run_once.py"
```
