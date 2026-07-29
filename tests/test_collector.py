from __future__ import annotations

import unittest

from pradata.collector import (
    classify_priority,
    classify_topic,
    extract_boe_records,
    extract_bopt_records,
    extract_link_records,
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
