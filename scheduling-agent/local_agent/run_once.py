"""Skeleton: one sweep of the inbox using the Claude Agent SDK and the scheduler MCP server.

UNTESTED. Needs: pip install claude-agent-sdk msal requests ; ANTHROPIC_API_KEY ; GRAPH_CLIENT_ID.
Read local_agent/README.md first.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SKILL = (ROOT / "skills" / "scheduling-assistant" / "SKILL.md").read_text(encoding="utf-8")
PLAYBOOK = (ROOT / "skills" / "scheduling-assistant" / "references" / "channels.md").read_text(encoding="utf-8")


def fetch_candidates() -> list[dict]:
    """Unread mail from the last 30 minutes that is not already categorised as handled.

    TODO: add to providers/graph.py:
        GET /me/mailFolders/inbox/messages?$filter=isRead eq false and receivedDateTime ge {iso}
            &$select=id,subject,from,receivedDateTime,bodyPreview,conversationId,categories
            &$orderby=receivedDateTime desc      (Prefer: outlook.body-content-type="text")
    and skip items whose categories include "Scheduled by assistant".
    """
    from scheduler.providers.graph import GraphProvider  # noqa: F401

    raise NotImplementedError("add GraphProvider.list_unread_since() before running")


async def handle(message: dict) -> None:
    from claude_agent_sdk import ClaudeAgentOptions, query  # type: ignore

    options = ClaudeAgentOptions(
        system_prompt=SKILL + "\n\n" + PLAYBOOK + "\n\nYou are running in sweep mode with SCHEDULER_PROVIDER=graph: "
        "omit the `busy` argument so the tools read the calendar themselves, and use create=true on confirm_meeting "
        "only after check_time passes and the client's automation level allows it.",
        mcp_servers={
            "scheduler": {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "scheduler.mcp_server"],
                "cwd": str(ROOT),
                "env": {**os.environ, "SCHEDULER_PROVIDER": "graph"},
            }
        },
        allowed_tools=[
            "mcp__scheduler__list_clients",
            "mcp__scheduler__propose_times",
            "mcp__scheduler__check_time",
            "mcp__scheduler__confirm_meeting",
            "mcp__scheduler__convert_time",
        ],
        permission_mode="acceptEdits",
        max_turns=12,
    )
    prompt = (
        f"New inbound email.\nFrom: {message['from']}\nSubject: {message['subject']}\n"
        f"Received: {message['receivedDateTime']}\nMessage id: {message['id']}\n\n{message['body']}\n\n"
        "Decide whether this is a scheduling request, a reply to our proposal, a counter-proposal, or unrelated, "
        "then follow the skill. Finish with a one-line status."
    )
    async for event in query(prompt=prompt, options=options):
        text = getattr(event, "result", None) or getattr(event, "content", None)
        if text:
            print(text)


async def main() -> None:
    for msg in fetch_candidates():
        await handle(msg)


if __name__ == "__main__":
    asyncio.run(main())
