from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pradata.telegram_publisher import (  # noqa: E402
    clean_text,
    publish_payload,
    read_json,
    send_telegram_message,
    wait_for_payload,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publica a Telegram només les novetats verificades de Pradell360."
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "telegram.json")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "telegram-state.json")
    parser.add_argument("--expected-data", type=Path, default=ROOT / "data" / "records.json")
    parser.add_argument("--pages-url", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    config = read_json(args.config)
    if not config.get("enabled", False) and not args.dry_run:
        print("Telegram desactivat a config/telegram.json; no s'envia res.")
        return 0
    if not config.get("enabled", False):
        print("Telegram desactivat; la simulació continua sense enviar res.")

    expected = read_json(args.expected_data)
    expected_updated_at = clean_text(expected.get("meta", {}).get("updated_at"))
    payload = wait_for_payload(
        clean_text(config.get("verified_api_url")),
        expected_updated_at,
        int(config.get("api_wait_seconds", 180)),
        int(config.get("api_poll_seconds", 10)),
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and not args.dry_run:
        raise RuntimeError(
            "Falta el secret TELEGRAM_BOT_TOKEN. El publicador no ha enviat cap missatge."
        )

    def send(channel: str, text: str, preview_url: str) -> int:
        return send_telegram_message(token, channel, text, preview_url)

    result = publish_payload(
        payload,
        config,
        args.state,
        send,
        dry_run=args.dry_run,
    )
    if not args.dry_run and args.pages_url.strip():
        state = read_json(args.state)
        state["pages_url"] = args.pages_url.strip()
        state["pages_verified_at"] = state.get("last_success_at", "")
        args.state.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "Telegram · "
        f"{result['verified']} registres verificats, "
        f"{result['eligible']} novetats elegibles, "
        f"{result['notifications']} missatges preparats, "
        f"{result['sent']} enviats, "
        f"{result['ignored_before_activation']} anteriors a l'activació ignorats, "
        f"{result['rejected']} registres descartats."
    )
    if args.dry_run and result.get("messages"):
        for index, message in enumerate(result["messages"], start=1):
            print(f"\n--- Simulació {index} ---\n{message}")
    if args.dry_run:
        print("Simulació completada: no s'ha enviat res ni s'ha modificat l'estat.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR Telegram: {error}", file=sys.stderr)
        raise SystemExit(1)
