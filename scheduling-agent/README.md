# Scheduling assistant

A calendar-scheduling agent for Claude Enterprise: it reads your Outlook calendar, proposes times that respect
a 30-minute buffer around every meeting, converts to each client's time zone, drafts the reply in your voice,
and books the Teams invite once the client says yes.

This folder is three things at once:

1. **A Python package** (`scheduler/`) with the deterministic logic, a CLI, and an MCP server. 37 tests.
2. **A Claude skill** (`skills/scheduling-assistant/`) that tells Claude how to run the workflow with the
   Microsoft 365 and Slack connectors.
3. **A Claude plugin** (`.claude-plugin/plugin.json` + `.mcp.json`) so the whole thing can be uploaded to an
   Enterprise org and installed per user.

Read `docs/ARCHITECTURE.md` for what works, what does not, and why. `docs/OPEN_QUESTIONS.md` lists what I
need from you.

## Quick start (this machine)

```bash
cd scheduling-agent
python -m pip install -r requirements.txt
python -m pytest -q
```

Try the engine against the sample calendar (week of 2 Nov 2026):

```bash
python -m scheduler.cli propose --client acme --name "Jane Doe" --channel email --topic kickoff --provider mock --now 2026-10-30T09:00:00-04:00
```

```bash
python -m scheduler.cli check --start 2026-11-02T10:30:00-05:00 --client acme --provider mock --now 2026-10-30T09:00:00-04:00
```

```bash
python -m scheduler.cli confirm --start 2026-11-03T16:30:00-05:00 --duration 30 --client acme --attendee jane.doe@acme.example --topic Kickoff --name "Jane Doe" --provider mock --now 2026-10-30T09:00:00-04:00
```

Use the MCP server from Claude Code in this folder:

```bash
claude mcp add --transport stdio scheduler -- python -m scheduler.mcp_server
```

Or load the whole plugin for one session:

```bash
claude --plugin-dir .
```

## Layout

| Path | Purpose |
|------|---------|
| `scheduler/availability.py` | Free-slot math: buffers, hours, lead time, DST, client hours, shortlist spread |
| `scheduler/tz.py` | IANA/Windows zone names, "ET"/"PT" labels, dual-zone formatting |
| `scheduler/service.py` | Use-cases: propose, check, confirm, Graph event payload |
| `scheduler/templates.py` + `templates/` | Reply wording; edit the `.txt` files to match your voice |
| `scheduler/config.py` | Loads `preferences.yaml` and `clients/` (flat files or per-client folders) |
| `scheduler/providers/` | `mock` (fixtures), `graph` (MSAL + Graph, untested here), `none` (Claude supplies busy list) |
| `scheduler/mcp_server.py` | Tools: `list_clients`, `propose_times`, `check_time`, `confirm_meeting`, `convert_time` |
| `scheduler/cli.py` | Same operations as JSON-printing commands |
| `skills/scheduling-assistant/` | The skill Claude follows, plus channel playbook, formats, sweep prompt |
| `clients/` | One YAML per client (`acme-corp.yaml`) or `Client Folder/client.yaml` |
| `preferences.yaml` | Your hours, buffer, lead time, voice |
| `fixtures/calendar_sample.json` | Demo calendar for the mock provider |
| `local_agent/` | Skeleton for the fully local Agent SDK path |
| `docs/` | Architecture, pushback, open questions |

## Moving it into your work Claude instance

**Option 1, Cowork or Claude Code on the work machine (fastest).** Copy this folder. Point
`SCHEDULER_CLIENTS_DIR` at your existing client folders (or drop a `client.yaml` in each). Run
`claude --plugin-dir .` or add the `.mcp.json`. Say "handle the scheduling email from Jane at Acme".

**Option 2, as an org plugin.** Zip this folder and upload it under Organization settings > Plugins & skills.
Teammates install it, connect their own Microsoft 365 account, and fill in their own `preferences.yaml`.

**Option 3, scheduled sweep.** Create a Claude Code cloud scheduled task with the prompt in
`skills/scheduling-assistant/references/inbox-sweep.md`, every 15 minutes on weekdays, with the Microsoft 365
connector attached and this skill enabled on your account.

**Option 4, fully local.** See `local_agent/README.md` and `scheduler/providers/graph.py`.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `SCHEDULER_HOME` | this folder | Where `preferences.yaml`, `clients/`, `templates/` live |
| `SCHEDULER_CLIENTS_DIR` | `$SCHEDULER_HOME/clients` | Your client folder tree |
| `SCHEDULER_PREFS` | `$SCHEDULER_HOME/preferences.yaml` | Preferences file |
| `SCHEDULER_PROVIDER` | `mock` | `mock`, `graph`, or `none` (Claude passes the busy list) |
| `SCHEDULER_MOCK_CALENDAR` | `fixtures/calendar_sample.json` | Mock calendar file |
| `GRAPH_CLIENT_ID`, `GRAPH_TENANT_ID`, `GRAPH_TOKEN_CACHE` | | Graph provider only |
