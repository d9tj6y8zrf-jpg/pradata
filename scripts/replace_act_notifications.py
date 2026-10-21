from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pradata.telegram_publisher import (  # noqa: E402
    Notification,
    clean_text,
    delete_telegram_message,
    fetch_json,
    read_json,
    render_notification,
    send_telegram_photo,
    theme_for,
    verified_record,
)


REPLACEMENTS = (
    (70, "aoc-actes-ple-15efb474d3d0e9c5ee"),
    (71, "aoc-actes-ple-a63bc59ed0c7331354"),
)


def main() -> int:
    config = read_json(ROOT / "config" / "telegram.json")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta el secret TELEGRAM_BOT_TOKEN.")
    payload = fetch_json(clean_text(config.get("verified_api_url")))
    records = {clean_text(item.get("id")): item for item in payload.get("records", []) if verified_record(item)}
    sent: list[tuple[int, int]] = []
    for old_message_id, record_id in REPLACEMENTS:
        record = records.get(record_id)
        if record is None:
            raise RuntimeError(f"No s'ha trobat el registre verificat {record_id}.")
        theme, label = theme_for(record)
        text, _preview_url = render_notification(
            Notification(theme, label, (record,)),
            clean_text(config.get("pradell360_base_url")),
            clean_text(config.get("channel_url")),
        )
        new_message_id = send_telegram_photo(
            token,
            clean_text(config.get("channel")),
            text,
            clean_text(config.get("photo_url")),
        )
        sent.append((old_message_id, new_message_id))

    for old_message_id, _new_message_id in sent:
        delete_telegram_message(token, clean_text(config.get("channel")), old_message_id)

    print("Substitucions completades: " + ", ".join(f"{old}->{new}" for old, new in sent))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR Telegram: {error}", file=sys.stderr)
        raise SystemExit(1)
