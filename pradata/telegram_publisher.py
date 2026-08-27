from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from typing import Any, Callable


MAX_TELEGRAM_TEXT = 4096
SAFE_TELEGRAM_TEXT = 3900
PRIORITY_ORDER = {
    "critica": 0,
    "alta": 1,
    "informativa": 2,
}

TOPIC_LABELS = {
    "administracio": "Administració",
    "contractacio": "Contractació",
    "govern": "Govern municipal",
    "municipi": "Vida al municipi",
    "personal": "Personal i ocupació",
    "pressupost": "Pressupost i fiscalitat",
    "subvencions": "Subvencions",
    "terminis_i_propietats": "Terminis i propietats",
    "territori": "Territori i medi ambient",
    "urbanisme_i_obres": "Urbanisme i obres",
}

THEMES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("tv-3223", "Carretera TV-3223", (r"\btv[\s-]?3223\b", r"\b3223\b")),
    ("n-420", "Carretera N-420", (r"\bn[\s-]?420\b",)),
    ("ferrocarril", "Ferrocarril", (r"ferrocarr", r"\badif\b", r"t[uú]nel")),
    ("energia", "Energia", (r"e[oò]lic", r"fotovolta", r"l[ií]nia el[eè]ctrica")),
    ("incendis", "Prevenció d’incendis", (r"incendi", r"forestal")),
    ("aigua", "Aigua i sanejament", (r"\baigua", r"sanejament", r"hidrogr")),
    ("pressupost", "Pressupost municipal", (r"pressupost", r"plantilla")),
    ("piscina", "Piscina municipal", (r"piscina",)),
    ("fiscalitat", "Fiscalitat municipal", (r"impost", r"fiscal", r"padr[oó]")),
    ("personal", "Personal i ocupació", (r"ocupaci[oó]", r"personal", r"convocat[oò]ria", r"pla[cç]a")),
)


@dataclass(frozen=True)
class Notification:
    key: str
    label: str
    records: tuple[dict[str, Any], ...]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_datetime(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} no conté un objecte JSON.")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verified_record(record: Any) -> bool:
    if not isinstance(record, dict) or record.get("status") != "verificat":
        return False
    return all(clean_text(record.get(field)) for field in ("id", "title", "source_name", "detected_at")) and bool(
        clean_text(record.get("published_at") or record.get("date"))
    )


def eligible_records(
    payload: dict[str, Any], state: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], int]:
    activation = parse_datetime(state.get("activation_at"))
    if activation is None:
        raise ValueError("L'estat de Telegram no conté una data d'activació vàlida.")

    acknowledged = {clean_text(item) for item in state.get("acknowledged_ids", []) if clean_text(item)}
    sent_record_ids = {
        clean_text(record_id)
        for sent_message in state.get("sent", [])
        if isinstance(sent_message, dict)
        for record_id in sent_message.get("record_ids", [])
        if clean_text(record_id)
    }
    already_published = acknowledged | sent_record_ids
    candidates: list[dict[str, Any]] = []
    ignored_before_activation: list[str] = []
    rejected = 0

    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("La resposta verificada no conté una llista de registres.")

    for record in records:
        if not verified_record(record):
            rejected += 1
            continue
        record_id = clean_text(record["id"])
        if record_id in already_published:
            continue
        detected_at = parse_datetime(record.get("detected_at"))
        if detected_at is None:
            rejected += 1
            continue
        if detected_at < activation:
            ignored_before_activation.append(record_id)
            continue
        candidates.append(record)

    candidates.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(clean_text(item.get("priority")), 9),
            clean_text(item.get("detected_at")),
            clean_text(item.get("id")),
        )
    )
    return candidates, ignored_before_activation, rejected


def theme_for(record: dict[str, Any]) -> tuple[str, str]:
    searchable = " ".join(
        clean_text(record.get(field)).lower()
        for field in ("title", "summary", "registry", "topic")
    )
    for key, label, patterns in THEMES:
        if any(re.search(pattern, searchable, flags=re.IGNORECASE) for pattern in patterns):
            return key, label
    topic = clean_text(record.get("topic"))
    return f"record:{clean_text(record['id'])}", TOPIC_LABELS.get(topic, "Informació pública")


def plan_notifications(records: list[dict[str, Any]], max_messages: int) -> list[Notification]:
    if max_messages < 1:
        raise ValueError("El límit de missatges ha de ser com a mínim 1.")

    grouped: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for record in records:
        key, label = theme_for(record)
        if key not in grouped:
            grouped[key] = (label, [])
        grouped[key][1].append(record)

    notifications = [
        Notification(key=key, label=label, records=tuple(items))
        for key, (label, items) in grouped.items()
    ]
    notifications.sort(
        key=lambda item: (
            min(PRIORITY_ORDER.get(clean_text(record.get("priority")), 9) for record in item.records),
            min(clean_text(record.get("detected_at")) for record in item.records),
            item.key,
        )
    )

    if len(notifications) <= max_messages:
        return notifications
    if max_messages == 1:
        merged = tuple(record for notification in notifications for record in notification.records)
        return [Notification("digest", "Resum de novetats verificades", merged)]

    leading = notifications[: max_messages - 1]
    remaining = tuple(
        record for notification in notifications[max_messages - 1 :] for record in notification.records
    )
    return [*leading, Notification("digest", "Altres novetats verificades", remaining)]


def entry_url(record: dict[str, Any], base_url: str) -> str:
    record_id = urllib.parse.quote(clean_text(record["id"]), safe="-._~")
    return (
        f"{base_url.rstrip('/')}/fitxa/pradata-{record_id}"
        "?utm_source=telegram&utm_medium=channel&utm_campaign=pradata"
    )


def display_date(value: Any) -> str:
    text = clean_text(value)
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return text or "no indicada"
    return f"{match.group(3)}.{match.group(2)}.{match.group(1)}"


def record_dates(record: dict[str, Any]) -> str:
    published = display_date(record.get("published_at") or record.get("date"))
    detected = display_date(record.get("detected_at"))
    return f"Publicada: {published} · Detectada: {detected}"


def append_subscription(message: str, channel_url: str) -> str:
    call_to_action = (
        "\n\n📲 Rep totes les novetats al canal de Telegram:\n"
        f"{channel_url}"
    )
    available = SAFE_TELEGRAM_TEXT - len(call_to_action)
    if len(message) > available:
        message = message[: max(0, available - 1)].rstrip() + "…"
    return message.rstrip() + call_to_action


def render_notification(notification: Notification, base_url: str, channel_url: str) -> tuple[str, str]:
    records = list(notification.records)
    first_url = entry_url(records[0], base_url)

    if len(records) == 1:
        record = records[0]
        summary = shorten(clean_text(record.get("summary")) or "Consulta la fitxa per veure'n el detall.", width=560, placeholder="…")
        recovery = "\nRecuperada en la revisió retrospectiva de 7 dies." if record.get("recovered") else ""
        message = (
            "🟢 Nova publicació verificada\n\n"
            f"{clean_text(record['title'])}\n\n"
            f"{record_dates(record)}\n"
            f"Font: {clean_text(record['source_name'])}"
            f"{recovery}\n\n"
            f"{summary}\n\n"
            "👉 Veure la publicació a Pradell360:\n"
            f"{first_url}"
        )
        return append_subscription(message, channel_url), first_url

    lines = [f"🟢 {len(records)} noves publicacions verificades · {notification.label}", ""]
    visible = records[:8]
    for index, record in enumerate(visible, start=1):
        lines.extend(
            [
                f"{index}. {shorten(clean_text(record['title']), width=210, placeholder='…')}",
                f"{record_dates(record)} · {clean_text(record['source_name'])}",
                entry_url(record, base_url),
                "",
            ]
        )
    if len(records) > len(visible):
        lines.extend(
            [
                f"I {len(records) - len(visible)} publicacions verificades més.",
                f"Consulta-les a {base_url.rstrip('/')}/#arxiu",
            ]
        )
    message = "\n".join(lines).strip()
    return append_subscription(message, channel_url), first_url


def fetch_json(url: str, timeout: int = 30) -> dict[str, Any]:
    separator = "&" if "?" in url else "?"
    request = urllib.request.Request(
        f"{url}{separator}v={int(time.time())}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "PRADATA-Telegram/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("L'API verificada no ha retornat un objecte JSON.")
    return payload


def wait_for_payload(
    api_url: str,
    expected_updated_at: str,
    wait_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    expected = parse_datetime(expected_updated_at)
    deadline = time.monotonic() + max(0, wait_seconds)
    last_updated = ""

    while True:
        payload = fetch_json(api_url)
        last_updated = clean_text(payload.get("meta", {}).get("updated_at"))
        current = parse_datetime(last_updated)
        if expected is None or (current is not None and current >= expected):
            return payload
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Pradell360 encara no reflecteix l'última execució de PRADATA "
                f"(esperada {expected_updated_at}; disponible {last_updated or 'sense data'})."
            )
        time.sleep(max(1, poll_seconds))


def entry_page_ready(html: str, url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    canonical_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    escaped_url = re.escape(canonical_url)
    has_canonical = bool(re.search(rf'<link[^>]+rel="canonical"[^>]+href="{escaped_url}"', html, re.IGNORECASE))
    has_image = bool(re.search(r'<meta[^>]+property="og:image"[^>]+content="https://pradell360\.cat/[^\"]+"', html, re.IGNORECASE))
    return has_canonical and has_image


def wait_for_entry_page(url: str, wait_seconds: int, poll_seconds: int) -> None:
    deadline = time.monotonic() + max(0, wait_seconds)
    last_error = ""
    while True:
        try:
            separator = "&" if "?" in url else "?"
            request = urllib.request.Request(
                f"{url}{separator}v={int(time.time())}",
                headers={
                    "Cache-Control": "no-cache",
                    "User-Agent": "Mozilla/5.0 (compatible; PRADATA/1.0; +https://pradell360.cat/)",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                html = response.read().decode("utf-8", errors="replace")
                if response.status == 200 and entry_page_ready(html, url):
                    return
                last_error = f"HTTP {response.status} o metadades incompletes"
        except (OSError, UnicodeError) as error:
            last_error = clean_text(error)
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "La fitxa de Pradell360 encara no és publicable i Telegram no enviarà l’avís: "
                f"{url} ({last_error or 'sense resposta'})."
            )
        time.sleep(max(1, poll_seconds))


def send_telegram_message(token: str, channel: str, text: str, preview_url: str) -> int:
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps(
        {
            "chat_id": channel,
            "text": text,
            "link_preview_options": {
                "url": preview_url,
                "prefer_large_media": True,
                "show_above_text": True,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        description = ""
        try:
            description = clean_text(json.loads(error.read().decode("utf-8")).get("description"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"Telegram ha respost HTTP {error.code}: {description or 'error no detallat'}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"No s'ha pogut contactar amb Telegram: {clean_text(error.reason)}") from None

    if not payload.get("ok") or not isinstance(payload.get("result"), dict):
        raise RuntimeError("Telegram no ha confirmat l'enviament.")
    message_id = payload["result"].get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("Telegram no ha retornat l'identificador del missatge.")
    return message_id


def edit_telegram_message(token: str, channel: str, message_id: int, text: str, preview_url: str) -> int:
    endpoint = f"https://api.telegram.org/bot{token}/editMessageText"
    body = json.dumps(
        {
            "chat_id": channel,
            "message_id": message_id,
            "text": text,
            "link_preview_options": {
                "url": preview_url,
                "prefer_large_media": True,
                "show_above_text": True,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        description = ""
        try:
            description = clean_text(json.loads(error.read().decode("utf-8")).get("description"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"Telegram ha respost HTTP {error.code}: {description or 'error no detallat'}") from None
    if not payload.get("ok") or not isinstance(payload.get("result"), dict):
        raise RuntimeError("Telegram no ha confirmat l’edició del missatge.")
    edited_id = payload["result"].get("message_id")
    if edited_id != message_id:
        raise RuntimeError("Telegram no ha retornat l’identificador esperat del missatge editat.")
    return edited_id


def publish_payload(
    payload: dict[str, Any],
    config: dict[str, Any],
    state_path: Path,
    send: Callable[[str, str, str], int],
    *,
    verify_entry: Callable[[str], None] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    state = read_json(state_path)
    candidates, ignored, rejected = eligible_records(payload, state)
    notifications = plan_notifications(candidates, int(config.get("max_messages_per_run", 3)))
    base_url = clean_text(config.get("pradell360_base_url"))
    channel = clean_text(config.get("channel"))
    channel_url = clean_text(config.get("channel_url"))
    if not base_url.startswith("https://"):
        raise ValueError("L'adreça base de Pradell360 ha de ser HTTPS.")
    if not channel.startswith("@"):
        raise ValueError("El canal de Telegram ha de tenir el format @nomdelcanal.")
    if not channel_url:
        channel_url = f"https://t.me/{channel.removeprefix('@')}"
    if not channel_url.startswith("https://t.me/"):
        raise ValueError("L'enllaç de subscripció ha de ser una adreça HTTPS de t.me.")

    result = {
        "verified": sum(1 for item in payload.get("records", []) if verified_record(item)),
        "eligible": len(candidates),
        "ignored_before_activation": len(ignored),
        "rejected": rejected,
        "notifications": len(notifications),
        "sent": 0,
    }
    if dry_run:
        result["messages"] = [render_notification(item, base_url, channel_url)[0] for item in notifications]
        return result

    acknowledged = {clean_text(item) for item in state.get("acknowledged_ids", []) if clean_text(item)}
    acknowledged.update(ignored)
    state["acknowledged_ids"] = sorted(acknowledged)
    state["last_checked_at"] = iso_now()
    state["source_updated_at"] = clean_text(payload.get("meta", {}).get("updated_at"))
    if ignored:
        write_json_atomic(state_path, state)

    sent_log = state.setdefault("sent", [])
    if not isinstance(sent_log, list):
        sent_log = []
        state["sent"] = sent_log

    for notification in notifications:
        text, preview_url = render_notification(notification, base_url, channel_url)
        if verify_entry is not None:
            for record in notification.records:
                verify_entry(entry_url(record, base_url))
        message_id = send(channel, text, preview_url)
        sent_at = iso_now()
        ids = [clean_text(record["id"]) for record in notification.records]
        acknowledged.update(ids)
        sent_log.append(
            {
                "sent_at": sent_at,
                "message_id": message_id,
                "record_ids": ids,
                "theme": notification.key,
            }
        )
        state["acknowledged_ids"] = sorted(acknowledged)
        state["sent"] = sent_log[-2000:]
        state["last_sent_at"] = sent_at
        write_json_atomic(state_path, state)
        result["sent"] += 1

    state["acknowledged_ids"] = sorted(acknowledged)
    state["last_checked_at"] = iso_now()
    state["last_success_at"] = state["last_checked_at"]
    state["source_updated_at"] = clean_text(payload.get("meta", {}).get("updated_at"))
    write_json_atomic(state_path, state)
    return result
