"""Load preferences and client profiles from YAML.

Layout (all paths overridable with environment variables so the work instance can point at its
existing per-client folder tree):

  SCHEDULER_HOME        default: the scheduling-agent/ directory this package lives in
  SCHEDULER_PREFS       default: $SCHEDULER_HOME/preferences.yaml
  SCHEDULER_CLIENTS_DIR default: $SCHEDULER_HOME/clients

Client profiles are discovered as:
  clients/<anything>.yaml                 one file per client, or
  clients/<Client Folder>/client.yaml     a file inside each existing client folder
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

import yaml

from .models import ClientProfile, Preferences

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_HOME = PACKAGE_DIR.parent


def home() -> Path:
    return Path(os.environ.get("SCHEDULER_HOME", DEFAULT_HOME)).resolve()


def prefs_path() -> Path:
    return Path(os.environ.get("SCHEDULER_PREFS", home() / "preferences.yaml"))


def clients_dir() -> Path:
    return Path(os.environ.get("SCHEDULER_CLIENTS_DIR", home() / "clients"))


def load_preferences(path: Optional[Path] = None) -> Preferences:
    p = path or prefs_path()
    if not p.exists():
        return Preferences()
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Preferences.model_validate(data)


def _client_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for p in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        if not p.name.startswith("_"):
            files.append(p)
    for p in sorted(root.glob("*/client.yaml")) + sorted(root.glob("*/client.yml")):
        files.append(p)
    return files


def load_clients(root: Optional[Path] = None) -> list[ClientProfile]:
    root = root or clients_dir()
    out: list[ClientProfile] = []
    for f in _client_files(root):
        with f.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if "id" not in data:
            # Folder-style profile: derive id from the folder name.
            data["id"] = (f.parent.name if f.name.startswith("client.") else f.stem).lower().replace(" ", "-")
        if "customer" not in data:
            data["customer"] = f.parent.name if f.name.startswith("client.") else f.stem
        profile = ClientProfile.model_validate(data)
        profile.source_path = str(f)
        out.append(profile)
    return out


def find_client(needle: str, clients: Optional[list[ClientProfile]] = None) -> Optional[ClientProfile]:
    """Match by id, customer name (case-insensitive, partial), contact email domain, or contact name."""
    clients = clients if clients is not None else load_clients()
    n = needle.lower().strip()
    if not n:
        return None
    for c in clients:
        if c.id.lower() == n or c.customer.lower() == n:
            return c
    for c in clients:
        if n in c.customer.lower() or n in c.id.lower():
            return c
    if "@" in n:
        domain = n.split("@", 1)[1]
        for c in clients:
            for ct in c.contacts:
                if ct.email and ct.email.lower().endswith("@" + domain):
                    return c
    for c in clients:
        if c.find_contact(n):
            return c
    return None


def save_client(profile: ClientProfile, root: Optional[Path] = None) -> Path:
    root = root or clients_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = Path(profile.source_path) if profile.source_path else root / f"{profile.id}.yaml"
    data = profile.model_dump(mode="json", exclude_none=True)
    with target.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return target
