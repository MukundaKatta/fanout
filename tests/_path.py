"""Make ``backend/app`` importable from the repo-root ``tests/`` package.

These stdlib-``unittest`` tests deliberately live at the repository root (not
under ``backend/tests/``) so they can be discovered and run with

    python3 -m unittest discover -s tests

from a clean checkout that has **no third-party dependencies installed**. The
only module they exercise is ``app.research``, which is pure-standard-library,
so the suite doubles as a fast dependency-free smoke check for the research
loop's scoring / parsing / dedup logic.

Importing this module prepends ``<repo>/backend`` to ``sys.path`` as a side
effect, so test modules can simply ``import tests._path`` before importing
``app.research``.
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")

if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
