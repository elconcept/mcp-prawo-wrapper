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
