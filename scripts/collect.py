from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pradata.collector import run_collection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consulta les fonts públiques i regenera PRADATA."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Carpeta arrel del projecte.",
    )
    args = parser.parse_args()
    result = run_collection(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False))
    if result["sources"] and result["responsive_sources"] == 0:
        print("Cap font no s'ha pogut consultar.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
