#!/usr/bin/env python3
"""Compatibility entry point for the coding route pack."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT.parent / "skill-routing" / "scripts"
sys.path.insert(0, str(SHARED))

from domain_router_cli import main  # noqa: E402


if __name__ == "__main__":
    main(ROOT / "references" / "pipeline-registry.json", ROOT.parent / ".skill-routing" / "profile.json")
