"""Export HTTP contracts without starting the application or accessing user data."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Configuration must not load a user's .env while describing the API.
os.environ["OPENFIC_SCHEMA_EXPORT"] = "1"
sys.path.insert(0, str(ROOT / "backend"))

from app.main import fastapi_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "frontend" / "openapi.json"
    )
    output = parser.parse_args().output
    output.write_text(
        json.dumps(fastapi_app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
