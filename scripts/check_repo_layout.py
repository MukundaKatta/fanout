#!/usr/bin/env python3
"""Validate Fanout's multi-surface repository contract."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require_file(relative: str) -> Path:
    path = ROOT / relative
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"Missing or empty required file: {relative}")
    return path


def main() -> None:
    require_file("backend/requirements.txt")
    require_file("web/package.json")
    manifest_path = require_file("extension/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("manifest_version") != 3:
        raise SystemExit("extension/manifest.json must stay on Manifest V3")
    for key in ("name", "version", "background", "permissions"):
        if key not in manifest:
            raise SystemExit(f"extension/manifest.json missing {key}")
    print("Fanout repository layout looks production-ready")


if __name__ == "__main__":
    main()
