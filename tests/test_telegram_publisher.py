from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pradata.telegram_publisher import (
    eligible_records,
    entry_page_ready,
    entry_url,
    plan_notifications,
    publish_payload,
    render_notification,
)


def record(
    record_id: str,
    title: str,
    *,
    detected_at: str = "2026-08-13T15:00:00+02:00",
    published_at: str = "2026-08-13",
    status: str = "verificat",
    topic: str = "municipi",
    source_name: str = "BOPT · Diputació de Tarragona",
) -> dict[str, object]:
    return {
        "id": record_id,
        "title": title,
        "published_at": published_at,
        "date": published_at,
        "detected_at": detected_at,
        "source_name": source_name,
        "source_id": "bopt",
        "summary": f"Resum verificat de {title}.",
        "topic": topic,
        "priority": "informativa",
        "status": status,
        "registry": "2026-00001",
        "url": "https://example.test/font-oficial",
    }


def state(
    acknowledged: list[str] | None = None,
    sent_record_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "version": 1,
        "activation_at": "2026-08-13T14:47:56+02:00",
        "acknowledged_ids": acknowledged or [],
        "sent": (
            [
                {
                    "message_id": 45,
                    "record_ids": sent_record_ids,
                }
            ]
            if sent_record_ids
            else []
        ),
    }


CONFIG = {
    "channel": "@pradellteixeta",
    "channel_url": "https://t.me/pradellteixeta",
    "pradell360_base_url": "https://pradell360.cat",
    "max_messages_per_run": 3,
}


class TelegramPublisherTests(unittest.TestCase):
    def test_only_new_verified_records_after_activation_are_eligible(self) -> None:
        payload = {
            "records": [
                record("already-seen", "Ja registrada"),
                record("pending", "Encara pendent", status="deteccio_automatica"),
                record("old", "Anterior", detected_at="2026-08-13T14:00:00+02:00"),
                record("new", "Nova publicació"),
            ]
        }
        candidates, ignored, rejected = eligible_records(payload, state(["already-seen"]))

        self.assertEqual([item["id"] for item in candidates], ["new"])
        self.assertEqual(ignored, ["old"])
        self.assertEqual(rejected, 1)

    def test_record_already_sent_to_telegram_is_not_repeated(self) -> None:
        payload = {
            "records": [
                record(
                    "dipta-impulsdipta-2026-0005675-pradell",
                    "Pla ImpulsDipta: bestreta per recondicionar edificis municipals",
                    published_at="2026-08-14",
                ),
                record("new", "Nova publicació"),
            ]
        }

        candidates, ignored, rejected = eligible_records(
            payload,
            state(sent_record_ids=["dipta-impulsdipta-2026-0005675-pradell"]),
        )

        self.assertEqual([item["id"] for item in candidates], ["new"])
        self.assertEqual(ignored, [])
        self.assertEqual(rejected, 0)

    def test_tv3223_records_from_different_sources_are_grouped(self) -> None:
        records = [
            record("one", "Aprovació del projecte de la TV-3223"),
            record(
                "two",
                "Relació de béns afectats per la carretera 3223",
                source_name="DOGC · Generalitat de Catalunya",
            ),
        ]

        notifications = plan_notifications(records, 3)

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].key, "tv-3223")
        self.assertEqual(len(notifications[0].records), 2)

    def test_message_limit_combines_the_overflow_into_a_digest(self) -> None:
        records = [record(str(index), f"Publicació independent {index}") for index in range(5)]

        notifications = plan_notifications(records, 3)

        self.assertEqual(len(notifications), 3)
        self.assertEqual(notifications[-1].key, "digest")
        self.assertEqual(len(notifications[-1].records), 3)

    def test_notifications_link_to_pradell360_not_the_official_source(self) -> None:
        item = record("bopt-123", "Nova publicació")
        notification = plan_notifications([item], 3)[0]

        message, preview = render_notification(
            notification,
            "https://pradell360.cat",
            "https://t.me/pradellteixeta",
        )

        expected = (
            "https://pradell360.cat/fitxa/pradata-bopt-123"
            "?utm_source=telegram&utm_medium=channel&utm_campaign=pradata&preview=2"
        )
        self.assertEqual(entry_url(item, "https://pradell360.cat"), expected)
        self.assertEqual(preview, expected)
        self.assertIn(expected, message)
        self.assertNotIn("example.test/font-oficial", message)
        self.assertIn("Publicada: 13.08.2026 · Detectada: 13.08.2026", message)
        self.assertIn("Rep totes les novetats al canal de Telegram", message)
        self.assertEqual(message.count("https://t.me/pradellteixeta"), 1)

    def test_entry_page_requires_its_canonical_url_and_social_image(self) -> None:
        canonical = "https://pradell360.cat/fitxa/pradata-bopt-123"
        url = f"{canonical}?utm_source=telegram&utm_medium=channel&utm_campaign=pradata&preview=2"
        html = (
            f'<link rel="canonical" href="{canonical}"/>'
            '<meta property="og:image" content="https://pradell360.cat/pradell360-compartir-v4.jpg"/>'
        )
        self.assertTrue(entry_page_ready(html, url))
        self.assertFalse(entry_page_ready('<title>Error 404</title>', url))

    def test_does_not_send_until_every_pradell360_entry_has_been_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(state()), encoding="utf-8")
            checked: list[str] = []

            def reject(url: str) -> None:
                checked.append(url)
                raise RuntimeError("fitxa no publicada")

            with self.assertRaisesRegex(RuntimeError, "fitxa no publicada"):
                publish_payload(
                    {"meta": {"updated_at": "2026-08-13T15:01:00+02:00"}, "records": [record("new", "Nova")]},
                    CONFIG,
                    state_path,
                    lambda *_args: self.fail("No pot enviar abans de verificar la fitxa"),
                    verify_entry=reject,
                )

            self.assertEqual(
                checked,
                [
                    "https://pradell360.cat/fitxa/pradata-new"
                    "?utm_source=telegram&utm_medium=channel&utm_campaign=pradata&preview=2"
                ],
            )

    def test_digest_also_contains_one_subscription_link(self) -> None:
        notification = plan_notifications(
            [record("one", "Publicació A"), record("two", "Publicació B")],
            3,
        )[0]

        message, _preview = render_notification(
            notification,
            "https://pradell360.cat",
            "https://t.me/pradellteixeta",
        )

        self.assertEqual(message.count("https://t.me/pradellteixeta"), 1)
        self.assertLessEqual(len(message), 3900)

    def test_dry_run_does_not_change_state_or_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            initial = state()
            state_path.write_text(json.dumps(initial), encoding="utf-8")

            result = publish_payload(
                {"meta": {"updated_at": "2026-08-13T15:01:00+02:00"}, "records": [record("new", "Nova")]},
                CONFIG,
                state_path,
                lambda *_args: self.fail("La simulació no pot enviar"),
                dry_run=True,
            )

            self.assertEqual(result["eligible"], 1)
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), initial)

    def test_successful_messages_are_saved_before_a_later_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(json.dumps(state()), encoding="utf-8")
            calls = 0

            def send(_channel: str, _text: str, _preview: str) -> int:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("fallada simulada")
                return 101

            payload = {
                "meta": {"updated_at": "2026-08-13T15:01:00+02:00"},
                "records": [
                    record("a", "Publicació A"),
                    record("b", "Publicació B"),
                ],
            }

            with self.assertRaisesRegex(RuntimeError, "fallada simulada"):
                publish_payload(payload, CONFIG, state_path, send)

            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["acknowledged_ids"]), 1)
            self.assertEqual(len(saved["sent"]), 1)
            self.assertEqual(saved["sent"][0]["message_id"], 101)


if __name__ == "__main__":
    unittest.main()
