"""Regresje wydzielenia tekstu ze źródłowego MCP (bez internetu)."""
from prawo_pl_mcp.native_judgment_text import extract_native_judgment_text as extract


def _meta(offset=0, limit=100, total=7686):
    return {
        "totalLength": total, "returnedLength": min(limit, total - offset),
        "offset": offset, "hasMore": offset + limit < total,
        "nextOffset": min(offset + limit, total) if offset + limit < total else None,
        "citations": [{"title": "V CSK 145/14"}],
    }


def _raw(offset=0, limit=100, total=7686, *, identity="166511"):
    text = ("Sygn. akt V CSK 145/14\n" + "T" * 400)[:limit]
    header = (
        "=== ORZECZENIE SAOS ===\n\n"
        "Sygnatura  : V CSK 145/14\n"
        f"ID SAOS    : {identity}\n"
        "SAOS URL   : https://www.saos.org.pl/judgments/166511\n\n"
        f"--- Tresc (znaki {offset}-{offset + limit} z {total} lacznie) ---\n"
    )
    suffix = (
        "\n[...] Skrocono. Nastepny fragment: "
        f"get_judgment(id={identity}, offset={offset + limit}, limit={limit}). "
        f"Pelna tresc: https://www.saos.org.pl/judgments/{identity}"
    )
    return header + text + suffix, text


def test_legacy_saos_decorated_text_exact_fragment():
    body, text = _raw()
    result = extract("saos", "166511", body, _meta(), offset=0, limit=100)
    assert result == text
    assert len(result) == _meta()["returnedLength"]
    assert "=== ORZECZENIE" not in result
    assert "[...] Skrocono" not in result


def test_direct_raw_and_structured_text():
    meta = _meta()
    text = "A" * 100
    assert extract("saos", "166511", text, meta, offset=0, limit=100) == text
    assert extract("saos", "166511", "", meta | {"text": text}, offset=0, limit=100) == text


def test_reject_mismatched_identity_and_ranges():
    body, _ = _raw(identity="99999")
    assert extract("saos", "166511", body, _meta(), offset=0, limit=100) is None
    body, _ = _raw(offset=100)
    assert extract("saos", "166511", body, _meta(), offset=0, limit=100) is None


def test_reject_truncated_text_or_unexpected_trailer():
    body, _ = _raw()
    assert extract("saos", "166511", body[:body.index("--- Tresc")], _meta(), offset=0, limit=100) is None
    assert extract("saos", "166511", body + "\nINJECTED", _meta(), offset=0, limit=100) is None


def test_reject_metadata_only_and_nsa_legacy_without_native_offsets():
    meta = _meta()
    assert extract("saos", "166511", "", meta, offset=0, limit=100) is None
    assert extract("nsa", "389F2C5B67", "=== ORZECZENIE CBOSA ===\nTreść",
                   {"citations": []}, offset=0, limit=100) is None


def test_last_partial_chunk():
    total = 110
    meta = _meta(offset=100, limit=100, total=total)
    text = "Z" * 10
    body = (
        "=== ORZECZENIE SAOS ===\nID SAOS : 166511\n"
        "--- Tresc (znaki 100-110 z 110 lacznie) ---\n" + text
    )
    assert extract("saos", "166511", body, meta, offset=100, limit=100) == text


def _nsa_body(text: str, *, offset=0, limit=5000, total=13348,
              identity="389F2C5B67") -> tuple[str, dict]:
    returned = len(text)
    more = offset + returned < total
    header = (
        "=== ORZECZENIE CBOSA (NSA / WSA) ===\n\n"
        "Sygnatura  : II SA/Wa 1353/19\n"
        f"ID CBOSA   : {identity}\n"
        "Sąd        : Wojewódzki Sąd Administracyjny w Warszawie\n"
        "Data       : 2020-03-03\n"
        "Źródło: https://orzeczenia.nsa.gov.pl/doc/389F2C5B67\n\n"
        f"--- Treść orzeczenia (znaki {offset}–{offset + returned} z {total}) ---\n"
    )
    suffix = (f"\nDalsza treść: get_judgment(doc_id=\"{identity}\", "
              f"offset={offset + returned}, limit={limit}).") if more else ""
    meta = {"totalLength": total, "returnedLength": returned,
            "offset": offset, "hasMore": more,
            "nextOffset": (offset + returned if more else None)}
    return header + text + suffix, meta


def test_nsa_pr2_two_chunks_reconstruct_exactly():
    # Wersja PR NSA #2 formatuje całe d.text przez .slice(0, limit).
    full = ("Sentencja. " + "Ochrona danych osobowych, zażalenie, sąd. " * 350)[:13348]
    total = len(full)
    first = full[:5000]
    second = full[5000:10000]
    last = full[10000:]
    parts = []
    for offset, txt in ((0, first), (5000, second), (10000, last)):
        raw, metadata = _nsa_body(txt, offset=offset, total=total)
        parsed = extract("nsa", "389F2C5B67", raw, metadata, offset=offset, limit=5000)
        assert parsed == txt
        parts.append(parsed)
    assert "".join(parts) == full


def test_nsa_reject_mismatch_and_wrong_suffix():
    raw, meta = _nsa_body("N" * 5000)
    assert extract("nsa", "0000000000", raw, meta, offset=0, limit=5000) is None
    assert extract("nsa", "389F2C5B67", raw + "INJECTED", meta, offset=0, limit=5000) is None
    assert extract("nsa", "389F2C5B67", raw.replace("0–5000", "0–4000"),
                   meta, offset=0, limit=5000) is None
    empty, last_meta = _nsa_body("N" * 200, offset=13148, total=13348)
    assert extract("nsa", "389F2C5B67", empty + "\nDalsza treść: "
                   "get_judgment(doc_id=\"389F2C5B67\", offset=13348, limit=5000).",
                   last_meta, offset=13148, limit=5000) is None
