from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Comprova que GitHub Pages ja serveix l'última sortida de PRADATA.")
    parser.add_argument("--expected", type=Path, default=ROOT / "data" / "records.json")
    parser.add_argument("--url", required=True)
    parser.add_argument("--wait-seconds", type=int, default=120)
    parser.add_argument("--poll-seconds", type=int, default=5)
    return parser.parse_args()

def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} no conté un objecte JSON.")
    return payload

def fetch_json(url: str) -> dict:
    separator = "&" if "?" in url else "?"
    request = urllib.request.Request(f"{url}{separator}v={int(time.time())}", headers={"Accept": "application/json", "Cache-Control": "no-cache", "User-Agent": "PRADATA-Pages-check/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub Pages no ha retornat un objecte JSON.")
    return payload

def matches(expected: dict, actual: dict) -> bool:
    expected_updated = str(expected.get("meta", {}).get("updated_at", "")).strip()
    actual_updated = str(actual.get("meta", {}).get("updated_at", "")).strip()
    expected_ids = [str(record.get("id", "")) for record in expected.get("records", [])]
    actual_ids = [str(record.get("id", "")) for record in actual.get("records", [])]
    return bool(expected_updated) and actual_updated == expected_updated and actual_ids == expected_ids

def main() -> int:
    args = arguments()
    expected = load_json(args.expected)
    deadline = time.monotonic() + max(0, args.wait_seconds)
    last_error = ""
    while True:
        try:
            if matches(expected, fetch_json(args.url)):
                print("GitHub Pages confirma la mateixa versió de dades que l'execució actual.")
                return 0
            last_error = "Pages encara no serveix la versió esperada."
        except (OSError, ValueError, json.JSONDecodeError) as error:
            last_error = str(error)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"No s'ha pogut confirmar GitHub Pages: {last_error}")
        time.sleep(max(1, args.poll_seconds))

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR Pages: {error}")
        raise SystemExit(1)
