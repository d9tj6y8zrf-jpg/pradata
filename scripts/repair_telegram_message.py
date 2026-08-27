from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pradata.telegram_publisher import (  # noqa: E402
    Notification,
    clean_text,
    edit_telegram_message,
    fetch_json,
    read_json,
    render_notification,
    theme_for,
    verified_record,
    wait_for_entry_page,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repara un avís existent perquè apunti a la fitxa de Pradell360.")
    parser.add_argument("--message-id", required=True, type=int)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "telegram.json")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    config = read_json(args.config)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta el secret TELEGRAM_BOT_TOKEN.")
    payload = fetch_json(clean_text(config.get("verified_api_url")))
    record = next(
        (item for item in payload.get("records", []) if clean_text(item.get("id")) == args.record_id and verified_record(item)),
        None,
    )
    if record is None:
        raise RuntimeError(f"No s’ha trobat el registre verificat {args.record_id}.")
    theme, label = theme_for(record)
    notification = Notification(theme, label, (record,))
    text, preview_url = render_notification(
        notification,
        clean_text(config.get("pradell360_base_url")),
        clean_text(config.get("channel_url")),
    )
    wait_for_entry_page(
        preview_url,
        int(config.get("entry_wait_seconds", 300)),
        int(config.get("entry_poll_seconds", 10)),
    )
    edit_telegram_message(
        token,
        clean_text(config.get("channel")),
        args.message_id,
        text,
        preview_url,
    )
    print(f"Missatge {args.message_id} reparat amb la fitxa {preview_url}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR Telegram: {error}", file=sys.stderr)
        raise SystemExit(1)
