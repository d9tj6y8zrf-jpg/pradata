from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / "site" / "index.html",
    ROOT / "site" / ".nojekyll",
    ROOT / "site" / "assets" / "styles.css",
    ROOT / "site" / "assets" / "app.js",
    ROOT / "site" / "data" / "records.json",
    ROOT / "site" / "data" / "records.csv",
    ROOT / "site" / "data" / "history.json",
    ROOT / "site" / "data" / "status.json",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.exists()]
    if missing:
        raise SystemExit(f"Falten fitxers: {', '.join(missing)}")

    for name in ("records.json", "history.json", "status.json"):
        with (ROOT / "site" / "data" / name).open("r", encoding="utf-8") as handle:
            json.load(handle)

    with (ROOT / "site" / "data" / "records.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        header = next(csv.reader(handle))
    if not {"title", "url", "source_name"}.issubset(header):
        raise SystemExit("El CSV no conté les columnes mínimes.")

    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    if "{{" in html or "}}" in html:
        raise SystemExit("La portada conserva marcadors sense substituir.")
    if 'lang="ca"' not in html:
        raise SystemExit("La portada no declara el català.")
    print("Sortida estàtica correcta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
