"""Run the independent OpenFic service manager."""

import sys
from io import TextIOWrapper
from typing import cast

from .cli import main

# Keep the public byte contract independent of Windows console and caller locale.
cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")
cast(TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8")

raise SystemExit(main())
