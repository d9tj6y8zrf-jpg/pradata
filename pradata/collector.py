from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ ja ho incorpora
    ZoneInfo = None


USER_AGENT = "Mozilla/5.0 (compatible; PRADATA/1.0; +https://github.com/)"
MAX_RECORDS = 750
MAX_HISTORY = 1500
REQUEST_TIMEOUT = 30


def compact_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())


def fold_text(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def sha(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def stable_record_id(source_id: str, url: str, title: str) -> str:
    return f"{source_id}-{sha(f'{url}|{fold_text(title)}', 18)}"


def now_local(timezone_name: str) -> datetime:
    if ZoneInfo:
        return datetime.now(ZoneInfo(timezone_name))
    return datetime.now(timezone.utc)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes


def fetch(url: str, accept: str = "text/html,application/xhtml+xml") -> FetchResult:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "ca,es;q=0.8,en;q=0.5",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(
        request, timeout=REQUEST_TIMEOUT, context=context
    ) as response:
        return FetchResult(
            url=response.geturl(),
            status=getattr(response, "status", 200),
            content_type=response.headers.get("Content-Type", ""),
            body=response.read(),
        )


def fetch_source_page(
    source: dict[str, Any],
    accept: str = "text/html,application/xhtml+xml",
) -> FetchResult:
    """Consulta una pàgina amb reintents i adreces alternatives segures."""
    urls = [source["url"], *source.get("fallback_urls", [])]
    attempts = max(1, min(int(source.get("fetch_attempts", 3)), 4))
    last_error: BaseException | None = None

    for url in dict.fromkeys(urls):
        for attempt in range(attempts):
            try:
                return fetch(url, accept=accept)
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code < 500 and error.code not in {408, 429}:
                    raise
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
            if attempt + 1 < attempts:
                time.sleep(attempt + 1)

    if last_error is not None:
        raise last_error
    raise urllib.error.URLError("No hi ha cap adreça configurada per a la font")


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False
        self._anchor: dict[str, Any] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            values = dict(attrs)
            self._anchor = {"href": values.get("href") or "", "parts": []}

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._anchor is not None:
            self.links.append(
                {
                    "href": self._anchor["href"],
                    "text": compact_text(" ".join(self._anchor["parts"])),
                }
            )
            self._anchor = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        value = compact_text(data)
        if not value:
            return
        self.text_parts.append(value)
        if self._in_title:
            self.title_parts.append(value)
        if self._anchor is not None:
            self._anchor["parts"].append(value)


class BoptCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, Any]] = []
        self._depth = 0
        self._card: dict[str, Any] | None = None
        self._card_depth = 0
        self._in_paragraph = 0
        self._in_anchor = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        if tag == "div":
            self._depth += 1
            classes = set((values.get("class") or "").split())
            if self._card is None and {"card", "bg-white"}.issubset(classes):
                self._card = {
                    "text": [],
                    "paragraph": [],
                    "publisher": [],
                    "href": "",
                }
                self._card_depth = self._depth
        if self._card is None:
            return
        if tag == "p":
            self._in_paragraph += 1
        if tag == "a":
            self._in_anchor += 1
            if not self._card["href"]:
                self._card["href"] = values.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        if self._card is not None:
            if tag == "p" and self._in_paragraph:
                self._in_paragraph -= 1
            if tag == "a" and self._in_anchor:
                self._in_anchor -= 1
            if tag == "div" and self._depth == self._card_depth:
                self.cards.append(self._card)
                self._card = None
                self._card_depth = 0
                self._in_paragraph = 0
                self._in_anchor = 0
        if tag == "div" and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._card is None:
            return
        value = compact_text(data)
        if not value:
            return
        self._card["text"].append(value)
        if self._in_paragraph:
            self._card["paragraph"].append(value)
        if self._in_anchor:
            self._card["publisher"].append(value)


def parse_html(body: bytes) -> LinkTextParser:
    parser = LinkTextParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser


def canonical_url(base_url: str, href: str) -> str:
    joined = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlsplit(joined)
    if parsed.scheme not in {"http", "https"}:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, val) for key, val in query if not key.lower().startswith("utm_")]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc.lower(), parsed.path, urllib.parse.urlencode(query), "")
    )


def link_allowed(url: str, source: dict[str, Any]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    base_host = urllib.parse.urlsplit(source["url"]).netloc.lower()
    allowed_hosts = {host.lower() for host in source.get("allowed_hosts", [base_host])}
    if parsed.netloc.lower() not in allowed_hosts:
        return False
    prefixes = source.get("path_prefixes", [])
    if prefixes and not any(parsed.path.startswith(prefix) for prefix in prefixes):
        return False
    return True


GENERIC_LINK_LABELS = {
    "més informació",
    "mes informació",
    "llegir més",
    "llegir mes",
    "veure més",
    "veure mes",
    "inici",
    "contacte",
    "guardar",
}


def extract_link_records(
    body: bytes,
    source: dict[str, Any],
    detected_at: str,
) -> list[dict[str, Any]]:
    parser = parse_html(body)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        url = canonical_url(source["url"], link["href"])
        title = compact_text(link["text"])
        if not url or not title or len(title) < 5:
            continue
        if fold_text(title) in GENERIC_LINK_LABELS:
            continue
        if not link_allowed(url, source) or url in seen:
            continue
        seen.add(url)
        topic = classify_topic(title, source.get("topic", "administracio"))
        priority = classify_priority(title)
        records.append(
            {
                "id": stable_record_id(source["id"], url, title),
                "title": title,
                "date": "",
                "detected_at": detected_at,
                "last_seen_at": detected_at,
                "source_id": source["id"],
                "source_name": source["name"],
                "source_url": source["url"],
                "url": url,
                "summary": (
                    "Enllaç detectat a la font pública. Consulteu l'original "
                    "per confirmar-ne el contingut i la data."
                ),
                "topic": topic,
                "priority": priority,
                "status": "deteccio_automatica",
                "registry": "",
            }
        )
    return records


def extract_bopt_records(
    body: bytes,
    page_url: str,
    source: dict[str, Any],
    keywords: Iterable[str],
    detected_at: str,
) -> list[dict[str, Any]]:
    parser = BoptCardParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    folded_keywords = [fold_text(value) for value in keywords]
    records: list[dict[str, Any]] = []
    for card in parser.cards:
        publisher = compact_text(" ".join(card["publisher"]))
        description = compact_text(" ".join(card["paragraph"]))
        all_text = compact_text(" ".join(card["text"]))
        if not any(keyword in fold_text(f"{publisher} {description}") for keyword in folded_keywords):
            continue
        registry_match = re.search(r"Registre\s*:\s*([0-9]{4}-[0-9A-Z-]+)", all_text, re.I)
        date_match = re.search(
            r"Data de publicaci[oó]\s*:\s*(\d{2}/\d{2}/\d{4})", all_text, re.I
        )
        published = ""
        if date_match:
            try:
                published = datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat()
            except ValueError:
                published = ""
        url = canonical_url(page_url, card["href"]) or page_url
        title = description or publisher or "Publicació del BOPT"
        records.append(
            {
                "id": stable_record_id(source["id"], url, title),
                "title": title,
                "date": published,
                "detected_at": detected_at,
                "last_seen_at": detected_at,
                "source_id": source["id"],
                "source_name": source["name"],
                "source_url": source["url"],
                "url": url,
                "summary": (
                    f"Publicació del BOPT atribuïda a {publisher}."
                    if publisher
                    else "Publicació detectada al BOPT."
                ),
                "topic": classify_topic(title, source.get("topic", "administracio")),
                "priority": classify_priority(title),
                "status": "deteccio_automatica",
                "registry": registry_match.group(1) if registry_match else "",
            }
        )
    return records


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _descendant_text(element: ET.Element, names: set[str]) -> str:
    for child in element.iter():
        if _local_name(child.tag) in names and child.text:
            return compact_text(child.text)
    return ""


def extract_boe_records(
    body: bytes,
    source: dict[str, Any],
    keywords: Iterable[str],
    detected_at: str,
    fallback_date: str,
) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    folded_keywords = [fold_text(value) for value in keywords]
    records: list[dict[str, Any]] = []
    for element in root.iter():
        if _local_name(element.tag) != "item":
            continue
        full_text = compact_text(" ".join(element.itertext()))
        if not any(keyword in fold_text(full_text) for keyword in folded_keywords):
            continue
        identifier = _descendant_text(element, {"identificador", "id"})
        title = _descendant_text(element, {"titulo", "titol", "title"})
        url = _descendant_text(element, {"url_html", "urlhtml"})
        if not url and identifier:
            url = f"https://www.boe.es/buscar/doc.php?id={urllib.parse.quote(identifier)}"
        if not title:
            title = full_text[:360] or "Publicació del BOE"
        url = canonical_url(source["url"], url) if url else source["url"]
        records.append(
            {
                "id": stable_record_id(source["id"], url, title),
                "title": title,
                "date": fallback_date,
                "detected_at": detected_at,
                "last_seen_at": detected_at,
                "source_id": source["id"],
                "source_name": source["name"],
                "source_url": source["url"],
                "url": url,
                "summary": "Coincidència detectada al sumari oficial del BOE.",
                "topic": classify_topic(title, source.get("topic", "administracio")),
                "priority": classify_priority(title),
                "status": "deteccio_automatica",
                "registry": identifier,
            }
        )
    return records


TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("terminis_i_propietats", ("al·leg", "alleg", "expropi", "béns afectats", "bens afectats")),
    ("contractacio", ("contract", "licit", "adjudic", "perfil del contractant")),
    ("subvencions", ("subvenci", "ajut", "concessi", "impulsdipta", "puosc")),
    ("pressupost", ("pressupost", "compte general", "liquidaci", "plantilla")),
    ("urbanisme_i_obres", ("urban", "obra", "projecte", "planejament", "llicèn", "llicen")),
    ("territori", ("camí", "cami", "carretera", "incendi", "ambient", "aigua")),
    ("govern", ("ple", "acta", "edicte", "ordenança", "ordenanca", "decret")),
    ("personal", ("personal", "ocupació", "ocupacio", "borsa", "selecció", "seleccio")),
]


def classify_topic(title: str, fallback: str = "administracio") -> str:
    value = fold_text(title)
    for topic, needles in TOPIC_RULES:
        if any(fold_text(needle) in value for needle in needles):
            return topic
    return fallback


def classify_priority(title: str) -> str:
    value = fold_text(title)
    critical = (
        "termini",
        "alleg",
        "expropi",
        "bens afectats",
        "ocupacio temporal",
        "recurs",
    )
    important = (
        "pressupost",
        "contract",
        "subvenci",
        "urban",
        "obra",
        "plantilla",
        "ordenanca",
        "planejament",
    )
    if any(fold_text(needle) in value for needle in critical):
        return "critica"
    if any(fold_text(needle) in value for needle in important):
        return "alta"
    return "informativa"


def content_fingerprint(body: bytes, content_type: str) -> str:
    if "html" in content_type.lower() or b"<html" in body[:1500].lower():
        parser = parse_html(body)
        normalized = compact_text(" ".join(parser.text_parts))
        return sha(normalized, 32)
    return sha(body.hex(), 32)


def collect_source(
    source: dict[str, Any],
    config: dict[str, Any],
    run_time: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    detected_at = run_time.isoformat(timespec="seconds")
    today = run_time.date()
    kind = source["kind"]
    records: list[dict[str, Any]] = []
    fingerprints: list[str] = []
    requests_ok = 0
    messages: list[str] = []
    last_http_status = 0

    def remember(result: FetchResult) -> None:
        nonlocal requests_ok, last_http_status
        requests_ok += 1
        last_http_status = result.status
        fingerprints.append(content_fingerprint(result.body, result.content_type))

    try:
        if kind in {"links", "watch"}:
            result = fetch_source_page(source)
            remember(result)
            if kind == "links":
                records.extend(extract_link_records(result.body, source, detected_at))

        elif kind == "bopt_recent":
            for offset in range(int(source.get("days", 8))):
                day = today - timedelta(days=offset)
                url = source["url_template"].format(date=day.isoformat())
                try:
                    result = fetch(url)
                except urllib.error.HTTPError as error:
                    if error.code in {400, 404}:
                        continue
                    if error.code == 500 and day.weekday() >= 5:
                        continue
                    messages.append(
                        f"Una data del BOPT no s'ha pogut llegir (HTTP {error.code})."
                    )
                    continue
                except (urllib.error.URLError, TimeoutError):
                    messages.append("Una data del BOPT no s'ha pogut llegir.")
                    continue
                remember(result)
                records.extend(
                    extract_bopt_records(
                        result.body,
                        result.url,
                        source,
                        config["keywords"],
                        detected_at,
                    )
                )

        elif kind == "boe_daily":
            for offset in range(int(source.get("days", 8))):
                day = today - timedelta(days=offset)
                url = source["url_template"].format(
                    date=day.isoformat(), date_compact=day.strftime("%Y%m%d")
                )
                try:
                    result = fetch(url, accept="application/xml")
                except urllib.error.HTTPError as error:
                    if error.code in {400, 404}:
                        continue
                    messages.append(
                        f"Una data del BOE no s'ha pogut llegir (HTTP {error.code})."
                    )
                    continue
                except (urllib.error.URLError, TimeoutError):
                    messages.append("Una data del BOE no s'ha pogut llegir.")
                    continue
                remember(result)
                records.extend(
                    extract_boe_records(
                        result.body,
                        source,
                        config["keywords"],
                        detected_at,
                        day.isoformat(),
                    )
                )
        else:
            raise ValueError(f"Tipus de font desconegut: {kind}")
    except (urllib.error.URLError, TimeoutError, ValueError, ET.ParseError) as error:
        messages.append(f"No s'ha pogut completar la lectura: {type(error).__name__}")

    state = "ok" if requests_ok else "error"
    if messages and requests_ok:
        state = "warning"
    status = {
        "id": source["id"],
        "name": source["name"],
        "url": source["url"],
        "state": state,
        "checked_at": detected_at,
        "http_status": last_http_status or "",
        "message": " ".join(dict.fromkeys(messages))
        or (
            "Font consultada correctament."
            if requests_ok
            else "No s'ha pogut consultar aquesta font."
        ),
        "item_count": len({record["id"] for record in records}),
        "fingerprint": sha("|".join(fingerprints), 32) if fingerprints else "",
        "track_fingerprint": kind in {"links", "watch"},
    }
    unique = {record["id"]: record for record in records}
    return list(unique.values()), status


def record_core_fingerprint(record: dict[str, Any]) -> str:
    fields = (
        "title",
        "date",
        "url",
        "summary",
        "topic",
        "priority",
        "status",
        "registry",
    )
    return sha(json.dumps([record.get(field, "") for field in fields], ensure_ascii=False))


def merge_results(
    records_doc: dict[str, Any],
    history_doc: dict[str, Any],
    state_doc: dict[str, Any],
    collected: list[tuple[list[dict[str, Any]], dict[str, Any]]],
    run_time: datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    timestamp = run_time.isoformat(timespec="seconds")
    records_by_id = {
        record["id"]: record for record in records_doc.get("records", []) if record.get("id")
    }
    history = list(history_doc.get("events", []))
    source_state = dict(state_doc.get("sources", {}))
    first_baseline = not source_state
    statuses: list[dict[str, Any]] = []

    for items, status in collected:
        statuses.append(status)
        previous_source = source_state.get(status["id"], {})
        old_fingerprint = previous_source.get("fingerprint", "")
        new_fingerprint = status.get("fingerprint", "")
        if (
            status.get("track_fingerprint")
            and old_fingerprint
            and new_fingerprint
            and old_fingerprint != new_fingerprint
        ):
            history.append(
                {
                    "id": f"event-{sha(f'{status['id']}|{timestamp}|source_changed', 20)}",
                    "detected_at": timestamp,
                    "type": "source_changed",
                    "record_id": "",
                    "source_id": status["id"],
                    "source_name": status["name"],
                    "title": f"Canvi detectat a {status['name']}",
                    "description": (
                        "La pàgina oficial ha canviat. El canvi tècnic no prova, "
                        "per si sol, que hi hagi una decisió administrativa nova."
                    ),
                    "url": status["url"],
                }
            )
        if status["state"] == "error" and previous_source.get("state") != "error":
            history.append(
                {
                    "id": f"event-{sha(f'{status['id']}|{timestamp}|source_error', 20)}",
                    "detected_at": timestamp,
                    "type": "source_error",
                    "record_id": "",
                    "source_id": status["id"],
                    "source_name": status["name"],
                    "title": f"No s'ha pogut consultar {status['name']}",
                    "description": (
                        "La cobertura d'aquesta execució és incompleta. "
                        "No s'interpreta com a absència de novetats."
                    ),
                    "url": status["url"],
                }
            )
        source_state[status["id"]] = {
            "fingerprint": status.get("fingerprint", ""),
            "state": status["state"],
            "checked_at": timestamp,
        }

        for item in items:
            existing = records_by_id.get(item["id"])
            if existing is None:
                records_by_id[item["id"]] = item
                event_type = "baseline" if first_baseline else "new"
                history.append(
                    {
                        "id": f"event-{sha(f'{item['id']}|{timestamp}|{event_type}', 20)}",
                        "detected_at": timestamp,
                        "type": event_type,
                        "record_id": item["id"],
                        "source_id": item["source_id"],
                        "source_name": item["source_name"],
                        "title": item["title"],
                        "description": (
                            "Referència incorporada a la línia de base inicial."
                            if first_baseline
                            else "Nova referència detectada a una font pública."
                        ),
                        "url": item["url"],
                    }
                )
                continue
            old_fingerprint = record_core_fingerprint(existing)
            new_fingerprint = record_core_fingerprint(item)
            item["detected_at"] = existing.get("detected_at", item["detected_at"])
            records_by_id[item["id"]] = {**existing, **item}
            if old_fingerprint != new_fingerprint:
                history.append(
                    {
                        "id": f"event-{sha(f'{item['id']}|{timestamp}|updated', 20)}",
                        "detected_at": timestamp,
                        "type": "updated",
                        "record_id": item["id"],
                        "source_id": item["source_id"],
                        "source_name": item["source_name"],
                        "title": item["title"],
                        "description": "Ha canviat una referència ja coneguda.",
                        "url": item["url"],
                    }
                )

    def record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
        return (
            record.get("date") or record.get("detected_at", ""),
            record.get("title", ""),
        )

    records = sorted(records_by_id.values(), key=record_sort_key, reverse=True)[:MAX_RECORDS]
    event_ids: set[str] = set()
    unique_history: list[dict[str, Any]] = []
    for event in sorted(
        history, key=lambda value: value.get("detected_at", ""), reverse=True
    ):
        if event["id"] in event_ids:
            continue
        event_ids.add(event["id"])
        unique_history.append(event)
    unique_history = unique_history[:MAX_HISTORY]

    records_doc = {
        "meta": {
            "project": "PRADATA",
            "municipality": "Pradell de la Teixeta",
            "updated_at": timestamp,
            "record_count": len(records),
            "notice": (
                "Inventari automatitzat i no exhaustiu. Cada dada s'ha de "
                "comprovar a la font oficial enllaçada."
            ),
        },
        "records": records,
    }
    history_doc = {
        "meta": {
            "updated_at": timestamp,
            "event_count": len(unique_history),
        },
        "events": unique_history,
    }
    state_doc = {"updated_at": timestamp, "sources": source_state}
    return records_doc, history_doc, state_doc, statuses


CSV_FIELDS = [
    "id",
    "title",
    "date",
    "detected_at",
    "last_seen_at",
    "source_name",
    "source_url",
    "url",
    "summary",
    "topic",
    "priority",
    "status",
    "registry",
]


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def build_site(
    root: Path,
    records_doc: dict[str, Any],
    history_doc: dict[str, Any],
    statuses: list[dict[str, Any]],
) -> None:
    site = root / "site"
    site_data = site / "data"
    assets = site / "assets"
    site_data.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    updated_at = records_doc["meta"]["updated_at"]
    template = (root / "templates" / "index.html").read_text(encoding="utf-8")
    index_html = (
        template.replace("{{UPDATED_AT}}", html.escape(updated_at))
        .replace("{{RECORD_COUNT}}", str(records_doc["meta"]["record_count"]))
        .replace("{{SOURCE_COUNT}}", str(len(statuses)))
    )
    (site / "index.html").write_text(index_html, encoding="utf-8", newline="\n")
    shutil.copyfile(root / "static" / "styles.css", assets / "styles.css")
    shutil.copyfile(root / "static" / "app.js", assets / "app.js")
    (site / ".nojekyll").write_text("", encoding="utf-8")

    write_json(site_data / "records.json", records_doc)
    write_json(site_data / "history.json", history_doc)
    write_json(
        site_data / "status.json",
        {
            "meta": {
                "updated_at": updated_at,
                "source_count": len(statuses),
                "successful_sources": sum(
                    1 for status in statuses if status["state"] == "ok"
                ),
            },
            "sources": statuses,
        },
    )
    write_csv(site_data / "records.csv", records_doc["records"])


def run_collection(root: Path) -> dict[str, Any]:
    config = load_json(root / "config" / "sources.json", {})
    timezone_name = config.get("timezone", "Europe/Madrid")
    run_time = now_local(timezone_name)
    data = root / "data"
    records_doc = load_json(data / "records.json", {"meta": {}, "records": []})
    history_doc = load_json(data / "history.json", {"meta": {}, "events": []})
    state_doc = load_json(data / "state.json", {"sources": {}})

    collected = [
        collect_source(source, config, run_time) for source in config.get("sources", [])
    ]
    records_doc, history_doc, state_doc, statuses = merge_results(
        records_doc, history_doc, state_doc, collected, run_time
    )

    write_json(data / "records.json", records_doc)
    write_json(data / "history.json", history_doc)
    write_json(data / "state.json", state_doc)
    write_json(
        data / "status.json",
        {
            "meta": {
                "updated_at": records_doc["meta"]["updated_at"],
                "source_count": len(statuses),
                "successful_sources": sum(
                    1 for status in statuses if status["state"] == "ok"
                ),
            },
            "sources": statuses,
        },
    )
    write_csv(data / "records.csv", records_doc["records"])
    build_site(root, records_doc, history_doc, statuses)

    successful = sum(1 for status in statuses if status["state"] != "error")
    return {
        "records": len(records_doc["records"]),
        "events": len(history_doc["events"]),
        "sources": len(statuses),
        "successful_sources": successful,
    }
