"""Microsoft Graph provider for the fully-local path (no Claude connector involved).

NOT exercised by the test suite: it needs a real tenant. Written against the Graph v1.0 docs and
left deliberately plain (requests + msal) so it is easy to read and audit.

Setup (an Entra admin usually has to do step 1):
  1. App registration in Entra ID: "Mobile and desktop applications" platform,
     redirect URI http://localhost, "Allow public client flows" = Yes.
     Delegated permissions: User.Read, Calendars.ReadWrite, Mail.ReadWrite, Mail.Send, MailboxSettings.Read.
  2. Environment:
       GRAPH_CLIENT_ID=<app id>
       GRAPH_TENANT_ID=<tenant id or 'organizations'>
       GRAPH_TOKEN_CACHE=~/.scheduler/msal_cache.bin   (optional)
  3. First run opens a browser for sign-in; after that the token cache refreshes silently.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models import BusyBlock, EventPayload

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read", "Calendars.ReadWrite", "Mail.ReadWrite", "Mail.Send", "MailboxSettings.Read"]


class GraphProvider:
    name = "graph"

    def __init__(self, client_id: str, tenant_id: str = "organizations", cache_path: Optional[Path] = None):
        try:
            import msal  # noqa: F401
            import requests  # noqa: F401
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pip install msal requests  (needed for SCHEDULER_PROVIDER=graph)") from e
        self.client_id = client_id
        self.tenant_id = tenant_id
        self.cache_path = cache_path or Path(os.path.expanduser("~/.scheduler/msal_cache.bin"))
        self._token: Optional[str] = None

    @classmethod
    def from_env(cls) -> "GraphProvider":
        cid = os.environ.get("GRAPH_CLIENT_ID")
        if not cid:
            raise RuntimeError("GRAPH_CLIENT_ID is required for the graph provider")
        cache = os.environ.get("GRAPH_TOKEN_CACHE")
        return cls(cid, os.environ.get("GRAPH_TENANT_ID", "organizations"), Path(cache) if cache else None)

    # --- auth -----------------------------------------------------------------------------------
    def _app(self):
        import msal

        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        app = msal.PublicClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}", token_cache=cache
        )
        return app, cache

    def token(self) -> str:
        if self._token:
            return self._token
        app, cache = self._app()
        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result:
            # Interactive browser sign-in; falls back to device code on headless boxes.
            try:
                result = app.acquire_token_interactive(SCOPES)
            except Exception:  # noqa: BLE001
                flow = app.initiate_device_flow(scopes=SCOPES)
                print(flow["message"])
                result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Graph auth failed: {result.get('error_description', result)}")
        if cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(cache.serialize(), encoding="utf-8")
        self._token = result["access_token"]
        return self._token

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
        h.update(extra or {})
        return h

    def _request(self, method: str, path: str, *, params: Optional[dict] = None, body: Optional[dict] = None,
                 headers: Optional[dict] = None) -> dict:
        import requests

        r = requests.request(method, f"{GRAPH}{path}", params=params, headers=self._headers(headers),
                             data=json.dumps(body) if body is not None else None, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph {method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    # --- calendar ----------------------------------------------------------------------------------
    def get_busy(self, start: datetime, end: datetime) -> list[BusyBlock]:
        """calendarView expands recurring series into instances, which is what we want."""
        params = {
            "startDateTime": start.astimezone(timezone.utc).isoformat(),
            "endDateTime": end.astimezone(timezone.utc).isoformat(),
            "$select": "subject,start,end,showAs,isAllDay,isCancelled,sensitivity",
            "$orderby": "start/dateTime",
            "$top": "200",
        }
        out: list[BusyBlock] = []
        path: Optional[str] = "/me/calendarView"
        headers = {"Prefer": 'outlook.timezone="UTC"'}
        while path:
            data = self._request("GET", path, params=params, headers=headers)
            for item in data.get("value", []):
                out.append(
                    BusyBlock(
                        start=_graph_dt(item["start"]),
                        end=_graph_dt(item["end"]),
                        subject=item.get("subject") if item.get("sensitivity") == "normal" else "(private)",
                        show_as=item.get("showAs", "busy"),
                        is_all_day=item.get("isAllDay", False),
                        is_cancelled=item.get("isCancelled", False),
                    )
                )
            next_link = data.get("@odata.nextLink")
            path = next_link.replace(GRAPH, "") if next_link else None
            params = None  # nextLink already carries the query
        return out

    def create_event(self, payload: EventPayload) -> dict:
        body = payload.model_dump(mode="json", exclude_none=True)
        data = self._request("POST", "/me/events", body=body)
        return {
            "id": data.get("id"),
            "webLink": data.get("webLink"),
            "onlineMeeting": data.get("onlineMeeting"),
            "invitesSent": True,  # Graph sends invitations to attendees on creation
        }

    def mailbox_timezone(self) -> str:
        return self._request("GET", "/me/mailboxSettings/timeZone").get("value", "UTC")

    # --- mail ---------------------------------------------------------------------------------------
    def _message(self, to: list[str], subject: str, body: str) -> dict:
        return {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }

    def create_draft(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        if reply_to_message_id:
            draft = self._request("POST", f"/me/messages/{reply_to_message_id}/createReplyAll")
            self._request("PATCH", f"/me/messages/{draft['id']}", body={"body": {"contentType": "Text", "content": body}})
            draft = self._request("GET", f"/me/messages/{draft['id']}", params={"$select": "id,webLink"})
        else:
            draft = self._request("POST", "/me/messages", body=self._message(to, subject, body))
        return {"id": draft.get("id"), "webLink": draft.get("webLink")}

    def send_mail(self, *, to: list[str], subject: str, body: str, reply_to_message_id: Optional[str] = None) -> dict:
        if reply_to_message_id:
            self._request("POST", f"/me/messages/{reply_to_message_id}/replyAll", body={"comment": body})
            return {"status": "sent", "inReplyTo": reply_to_message_id}
        self._request("POST", "/me/sendMail", body={"message": self._message(to, subject, body), "saveToSentItems": True})
        return {"status": "sent"}


def _graph_dt(obj: dict) -> datetime:
    from ..tz import resolve_zone

    raw = obj["dateTime"]
    if "." in raw:
        head, frac = raw.split(".", 1)
        raw = f"{head}.{frac[:6]}"
    dt = datetime.fromisoformat(raw.replace("Z", ""))
    return dt.replace(tzinfo=resolve_zone(obj.get("timeZone") or "UTC"))
