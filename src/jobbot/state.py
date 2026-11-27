"""Persistent state (JSON). In GitHub Actions it lives on the `jobbot-state` branch."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from . import config


class State:
    def __init__(self, path=None):
        self.path = path or (config.STATE_DIR / "state.json")
        self.d = {"jobs": {}, "roles": {}, "applied_by_day": {}, "emails_by_day": {}, "baselined": [],
                  "flags_sent": [], "contacted": {}, "dry_roles": []}
        if self.path.exists():
            self.d.update(json.loads(self.path.read_text(encoding="utf8")))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, indent=1, sort_keys=True), encoding="utf8")

    # --- time helpers
    @staticmethod
    def today() -> str:
        tz = ZoneInfo(config.profile().get("timezone", "America/New_York"))
        return datetime.now(tz).date().isoformat()

    # --- seen / dedupe
    def seen(self, posting_key: str) -> bool:
        return posting_key in self.d["jobs"]

    def mark_seen(self, posting_key: str, status: str):
        self.d["jobs"][posting_key] = {"status": status, "at": datetime.now(timezone.utc).isoformat()}

    def role_done(self, role_key: str, live: bool = True) -> bool:
        """True if we already applied (or attempted) this company+role. Dry-run sims only block other dry runs, never a live run."""
        return role_key in self.d["roles"] or (not live and role_key in self.d["dry_roles"])

    def mark_dry_role(self, role_key: str):
        if role_key not in self.d["dry_roles"]:
            self.d["dry_roles"].append(role_key)

    def mark_role(self, role_key: str, status: str):
        self.d["roles"][role_key] = {"status": status, "day": self.today()}

    # --- baseline (first run per source must not treat the whole board as new)
    def baselined(self, source_id: str) -> bool:
        return source_id in self.d["baselined"]

    def set_baselined(self, source_id: str):
        if source_id not in self.d["baselined"]:
            self.d["baselined"].append(source_id)

    # --- daily counters
    def applied_today(self) -> int:
        return self.d["applied_by_day"].get(self.today(), 0)

    def add_applied(self):
        t = self.today()
        self.d["applied_by_day"][t] = self.d["applied_by_day"].get(t, 0) + 1

    def emails_today(self) -> int:
        return self.d["emails_by_day"].get(self.today(), 0)

    def add_email(self):
        t = self.today()
        self.d["emails_by_day"][t] = self.d["emails_by_day"].get(t, 0) + 1

    # --- flags
    def flag_sent(self, key: str) -> bool:
        return key in self.d["flags_sent"]

    def add_flag(self, key: str):
        self.d["flags_sent"].append(key)
