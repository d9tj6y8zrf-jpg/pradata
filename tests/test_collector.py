from __future__ import annotations

import unittest
import urllib.error
from datetime import datetime
from unittest.mock import patch

from pradata.collector import (
    FetchResult,
    classify_priority,
    classify_topic,
    collect_source,
    extract_boe_records,
    extract_bopt_records,
    extract_link_records,
    fetch_source_page,
    matches_geographic_scope,
    stable_record_id,
)


class CollectorTests(unittest.TestCase):
    def test_stable_id_is_deterministic(self) -> None:
        first = stable_record_id("font", "https://example.test/a", "Títol")
        second = stable_record_id("font", "https://example.test/a", "Títol")
        self.assertEqual(first, second)

    def test_classification_surfaces_deadlines(self) -> None:
        title = "Informació pública amb termini d'al·legacions i béns afectats"
        self.assertEqual(classify_priority(title), "critica")
        self.assertEqual(classify_topic(title), "terminis_i_propietats")

    def test_accepts_teixeta_only_with_relevant_territorial_context(self) -> None:
        self.assertTrue(
            matches_geographic_scope(
                "Obres de seguretat a l'N-420 al coll de la Teixeta",
                ["Pradell de la Teixeta", "Pradell"],
                ["Teixeta"],
                ["coll", "carretera", "N-420"],
            )
        )
        self.assertFalse(
            matches_geographic_scope(
                "Restaurant La Teixeta presenta un nou menú",
                ["Pradell de la Teixeta", "Pradell"],
                ["Teixeta"],
                ["coll", "carretera", "N-420"],
            )
        )

    def test_rejects_a_street_named_after_pradell_in_another_municipality(self) -> None:
        self.assertFalse(
            matches_geographic_scope(
                "Modificació urbanística al carrer Pradell de la Teixeta de Reus",
                ["Pradell de la Teixeta", "Pradell"],
                ["Teixeta"],
                ["urbanística"],
                ["carrer Pradell de la Teixeta"],
            )
        )

    @patch("pradata.collector.fetch")
    def test_bopt_queries_pradell_and_teixeta(self, mocked_fetch) -> None:
        mocked_fetch.return_value = FetchResult(
            url="https://aplicacions.dipta.cat/bopt/web/anteriors/2026-08-10",
            status=200,
            content_type="text/html",
            body=b"<html></html>",
        )
        source = {
            "id": "bopt",
            "name": "BOPT",
            "kind": "bopt_recent",
            "url": "https://aplicacions.dipta.cat/bopt/",
            "url_template": "https://example.test/{date}?q={term}",
            "search_terms": ["Pradell", "Teixeta"],
            "days": 1,
            "topic": "administracio",
        }
        config = {
            "keywords": ["Pradell de la Teixeta", "Pradell"],
            "related_keywords": ["Teixeta"],
            "related_context_keywords": ["coll", "carretera"],
            "excluded_phrases": ["carrer Pradell de la Teixeta"],
        }

        collect_source(source, config, datetime.fromisoformat("2026-08-10T08:00:00+02:00"))

        self.assertEqual(mocked_fetch.call_count, 2)
        requested_urls = [call.args[0] for call in mocked_fetch.call_args_list]
        self.assertTrue(any("q=Pradell" in url for url in requested_urls))
        self.assertTrue(any("q=Teixeta" in url for url in requested_urls))

    def test_extracts_only_allowed_links(self) -> None:
        body = b"""
        <html><body>
          <a href="/ca/noticies/nova-publicacio">Nova publicaci\xc3\xb3</a>
          <a href="/ca/contacte">Contacte</a>
        </body></html>
        """
        source = {
            "id": "web",
            "name": "Web",
            "url": "https://example.test/ca",
            "topic": "municipi",
            "path_prefixes": ["/ca/noticies/"],
        }
        records = extract_link_records(body, source, "2026-07-29T08:00:00+02:00")
        self.assertEqual(len(records), 1)
        self.assertIn("Nova publicació", records[0]["title"])

    @patch("pradata.collector.time.sleep", return_value=None)
    @patch("pradata.collector.fetch")
    def test_source_page_retries_after_temporary_error(self, mocked_fetch, _sleep) -> None:
        expected = FetchResult(
            url="https://example.test/ca",
            status=200,
            content_type="text/html",
            body=b"<html></html>",
        )
        mocked_fetch.side_effect = [urllib.error.URLError("temporal"), expected]
        source = {"url": "https://example.test/ca", "fetch_attempts": 3}

        self.assertEqual(fetch_source_page(source), expected)
        self.assertEqual(mocked_fetch.call_count, 2)

    @patch("pradata.collector.time.sleep", return_value=None)
    @patch("pradata.collector.fetch")
    def test_source_page_uses_fallback_after_retries(self, mocked_fetch, _sleep) -> None:
        expected = FetchResult(
            url="https://alternative.example.test/ca",
            status=200,
            content_type="text/html",
            body=b"<html></html>",
        )
        mocked_fetch.side_effect = [
            urllib.error.URLError("temporal"),
            urllib.error.URLError("temporal"),
            expected,
        ]
        source = {
            "url": "https://example.test/ca",
            "fallback_urls": ["https://alternative.example.test/ca"],
            "fetch_attempts": 2,
        }

        self.assertEqual(fetch_source_page(source), expected)
        self.assertEqual(mocked_fetch.call_args_list[-1].args[0], "https://alternative.example.test/ca")

    def test_extracts_bopt_card(self) -> None:
        body = """
        <div class="card bg-white mb-4">
          <div class="card-body">
            <h3><a href="/bopt/web/anunci/1/exemple">AJUNTAMENT PRADELL DE LA TEIXETA</a></h3>
            <p>Pressupost general per a 2026. Aprovació definitiva.</p>
            <ul>
              <li>Registre: 2026-00001</li>
              <li>Data de publicació: 29/07/2026</li>
            </ul>
          </div>
        </div>
        """.encode()
        source = {
            "id": "bopt",
            "name": "BOPT",
            "url": "https://aplicacions.dipta.cat/bopt/",
            "topic": "administracio",
        }
        records = extract_bopt_records(
            body,
            "https://aplicacions.dipta.cat/bopt/web/anteriors/2026-07-29",
            source,
            ["Pradell de la Teixeta"],
            "2026-07-29T08:00:00+02:00",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["registry"], "2026-00001")
        self.assertEqual(records[0]["date"], "2026-07-29")
        self.assertEqual(records[0]["priority"], "alta")

    def test_extracts_boe_item(self) -> None:
        body = b"""<?xml version="1.0" encoding="utf-8"?>
        <response><data><sumario><diario><seccion><item>
          <identificador>BOE-B-2026-1</identificador>
          <titulo>Anuncio referit a Pradell de la Teixeta</titulo>
          <url_html>https://www.boe.es/diario_boe/txt.php?id=BOE-B-2026-1</url_html>
        </item></seccion></diario></sumario></data></response>"""
        source = {
            "id": "boe",
            "name": "BOE",
            "url": "https://www.boe.es/",
            "topic": "administracio",
        }
        records = extract_boe_records(
            body,
            source,
            ["Pradell de la Teixeta"],
            "2026-07-29T08:00:00+02:00",
            "2026-07-29",
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["registry"], "BOE-B-2026-1")


if __name__ == "__main__":
    unittest.main()
