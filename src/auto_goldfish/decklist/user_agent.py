"""Shared User-Agent string for outbound decklist API calls.

Scryfall rejects requests that send an HTTP library's default User-Agent
with ``400 bad_request`` (subcode ``generic_user_agent``), so every outbound
call must identify this project.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    try:
        return version("auto_goldfish")
    except PackageNotFoundError:
        return "dev"


def default_user_agent() -> str:
    """Return a User-Agent identifying this project by name + GitHub URL."""
    return f"auto-goldfish/{_package_version()} (+https://github.com/jmusiel/auto-goldfish)"
