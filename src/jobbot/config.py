"""Config loading. Everything user-editable lives in /config (YAML)."""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
import yaml

ROOT = Path(os.environ.get("JOBBOT_ROOT", Path(__file__).resolve().parents[2]))
CONFIG_DIR = ROOT / "config"
STATE_DIR = ROOT / "state"
OUT_DIR = ROOT / "out"
TEMPLATE = ROOT / "templates" / "Sandip_Resume_Template.docx"
HARD_DAILY_CEILING = 20  # spec: 15-20 per day, never more


def _load(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf8")) or {}


@lru_cache(maxsize=1)
def profile() -> dict:
    return _load("profile.yaml")


@lru_cache(maxsize=1)
def guardrails() -> dict:
    g = _load("guardrails.yaml")
    g["daily_auto_apply_cap"] = min(int(g.get("daily_auto_apply_cap", 15)), HARD_DAILY_CEILING)
    return g


@lru_cache(maxsize=1)
def companies() -> dict:
    return _load("companies.yaml")


@lru_cache(maxsize=1)
def bank() -> dict:
    return _load("bullet_bank.yaml")


def mode() -> str:
    m = os.environ.get("JOBBOT_MODE") or guardrails().get("mode_default", "dry_run")
    if m not in ("dry_run", "live"):
        raise ValueError(f"JOBBOT_MODE must be dry_run or live, got {m!r}")
    return m


def is_live() -> bool:
    return mode() == "live"


def reset_caches() -> None:
    for f in (profile, guardrails, companies, bank):
        f.cache_clear()
