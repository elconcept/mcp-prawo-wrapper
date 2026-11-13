"""Offline identity tests for the official MS resolver."""
import unittest
import xml.etree.ElementTree as ET

from server import checked_document, normalize_id

DOC = "151020250000503_I_C_000270_2015_Uz_2016-04-07_001"
META = f'<judgement id="{DOC}"><signature>I C 270/15</signature><date>2016-01-19 01:00:00.0 CET</date><courtId>15102025</courtId><departmentId>503</departmentId><type>SENTENCE, REASON</type></judgement>'
BODY = '<xPart xFlag="published" xFromPg="1" xToPage="9"><xBlock><xText>Sygn. akt: I C 270/15</xText><xText>WYROK W IMIENIU RZECZYPOSPOLITEJ POLSKIEJ</xText><xText>Sąd Rejonowy w Bytowie I Wydział Cywilny</xText><xText>Dnia 19 stycznia 2016 r. Zasądza 425 zł za kartę pojazdu, uwzględniając uzasadnienie.</xText></xBlock></xPart>'


class ExactIdentityTests(unittest.TestCase):
    def test_accepts_exact_full_id_and_extracts_text(self):
        doc = checked_document(DOC, ET.fromstring(META), ET.fromstring(BODY))
        self.assertTrue(doc["identity_verified"])
        self.assertEqual(doc["signature"], "I C 270/15")
        self.assertEqual(doc["date"], "2016-01-19")
        self.assertIn("Sąd Rejonowy w Bytowie", doc["court"])
        self.assertIn("WYROK", doc["content_text"])
        self.assertEqual(doc["document_id"], "ms:" + DOC)

    def test_rejects_metadata_id_mismatch(self):
        with self.assertRaisesRegex(ValueError, "different document ID"):
            checked_document(DOC, ET.fromstring(META.replace(DOC, "other")), ET.fromstring(BODY))

    def test_rejects_signature_collision(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            checked_document(DOC, ET.fromstring(META.replace("I C 270/15", "I C 999/15")), ET.fromstring(BODY))

    def test_rejects_partial_xml_page_range(self):
        with self.assertRaisesRegex(ValueError, "partial page range"):
            checked_document(DOC, ET.fromstring(META), ET.fromstring(BODY.replace('xFromPg="1"', 'xFromPg="2"')))

    def test_rejects_bad_input(self):
        for value in ("ms:../../secrets", "ms:https://evil.example/", "", "I C 270/15"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_id(value)


if __name__ == "__main__":
    unittest.main()
