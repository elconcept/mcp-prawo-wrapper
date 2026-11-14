"""Offline acceptance gates for Repertorium snippets -> bounded Markdown full text."""
from __future__ import annotations

import json

import pytest

import prawo_pl_mcp.server as server
from prawo_pl_mcp import hydrate, md_store
from prawo_pl_mcp.pool import _timeout_for
from prawo_pl_mcp.registry import SOURCES


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(md_store, "ROOT", tmp_path)
    return tmp_path


def hit(document_id="saos:123"):
    return {"document_id": document_id, "tytul": "Wyrok II C 100/26",
            "fragment": "Oryginalny fragment wyników Repertorium.",
            "zrodlo_url": "https://example.org/123", "data": "2026-05-12"}


async def test_success_stores_full_source_without_inline_fulltext(store):
    async def invoke(source, tool, args):
        assert (source, tool, args) == (
            "saos", "get_judgment", {"id": 123, "offset": 0, "limit": 20000}
        )
        document = "Pełny tekst orzeczenia. " * 600
        return (f"=== ORZECZENIE SAOS ===\n\nID SAOS    : 123\n\n"
                f"--- Tresc (znaki 0-{len(document)} z {len(document)} lacznie) ---\n"
                + document)

    result = await hydrate.hydrate({"trafienia": [hit()], "total": 1}, "wyrok", invoke)
    entry = result["trafienia"][0]
    assert result["total"] == 1
    assert entry["fragment"] == hit()["fragment"]
    assert entry["fulltext_status"] == "full"
    assert entry["md_file"].startswith(md_store.REL_ROOT + "/saos/")
    assert "Pełny tekst orzeczenia" not in json.dumps(result, ensure_ascii=False)
    saved = store / entry["md_file"].removeprefix(md_store.REL_ROOT + "/")
    assert saved.is_file()
    text = saved.read_text()
    assert "content_status: \"full\"" in text
    assert "canonical_document_id: \"saos:123\"" in text
    page = await md_store.read(entry["md_file"], 1)
    assert page["has_more"]
    assert page["content_status"] == "full"
    assert page["next_call"]["arguments"]["page"] == 2
    assert page["next_call"]["arguments"]["extra"]["expected_sha256"] == page["content_sha256"]
    following = await md_store.read(entry["md_file"], 2, page["content_sha256"])
    assert following["page"] == 2


async def test_unknown_hit_survives_as_explicit_fragment(store):
    async def never(*_):
        raise AssertionError("Must not invent a source call")
    item = hit("unknown:abc")
    item["tytul"] = ""
    result = await hydrate.hydrate({"trafienia": [item]}, "x", never)
    out = result["trafienia"][0]
    assert out["fulltext_status"] == "fragment_only"
    assert out["user_disclosure_required"]
    assert "Nie udało się uzyskać pełnej treści" in out["warning"]
    saved = await md_store.read(out["md_file"], 1)
    assert saved["user_disclosure_required"]
    assert saved["content_status"] == "fragment_only"


async def test_metadata_only_never_qualifies_as_full(store):
    async def native(*_):
        return json.dumps({"id": 123, "title": "Wyrok", "url": "https://example.org"})
    result = await hydrate.hydrate({"trafienia": [hit()]}, "x", native)
    out = result["trafienia"][0]
    assert out["fulltext_status"] == "fragment_only"
    assert "metadata" in out["warning"]


def test_truncated_json_is_rejected():
    with pytest.raises(LookupError, match="incomplete"):
        hydrate._decode('{"text":"A very long document with real content present", "has_more":true}')


async def test_path_traversal_and_symlinks_are_forbidden(store, tmp_path):
    with pytest.raises(ValueError):
        await md_store.read("../passwd.md", 1)
    outside = tmp_path.parent / "other_sources"
    outside.mkdir(exist_ok=True)
    (outside / "secret.md").write_text("private")
    (store / "escaped").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        await md_store.read("escaped/secret.md", 1)
    with pytest.raises(ValueError):
        await md_store.write(hit("escaped:id"), "escaped", "Long but unresolved fragment",
                             "fragment_only")


async def test_same_document_has_deterministic_name_and_no_downgrade(store):
    original = "Pełny wyrok i uzasadnienie. " * 40
    first = await md_store.write(hit(), "saos", original, "full")
    assert await md_store.write(hit(), "saos", original, "full") == first
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        await md_store.write(hit(), "saos", "fragment not complete", "fragment_only")
    assert (await md_store.read(first, 1))["content_status"] == "full"


async def test_page_version_check_fails_closed(store):
    path = await md_store.write(hit(), "saos", "Content " * 2000, "full")
    await md_store.read(path, 1)
    with pytest.raises(ValueError, match="changed between page"):
        await md_store.read(path, 2, "0" * 64)
    saved = store / path.removeprefix(md_store.REL_ROOT + "/")
    saved.write_text(saved.read_text().replace("Content ", "Changed ", 1))
    with pytest.raises(ValueError, match="integrity"):
        await md_store.read(path, 1)


async def test_repertorium_json_and_unchanged_explicit_source(store, monkeypatch):
    calls = []

    class Pool:
        async def call(self, source, tool, args):
            calls.append((source.id, tool, args))
            if source.id == "repertorium":
                return json.dumps({"trafienia": [hit()], "total": 1})
            if source.id == "saos":
                if tool == "get_judgment":
                    return "Oryginalna pełna treść dokumentu. " * 30
                return "Natywne wyszukiwanie bez modyfikacji"
            raise AssertionError(source.id)

    monkeypatch.setattr(server, "POOL", Pool())
    result = json.loads(await server.pl_search(query="szkoda"))
    assert result["trafienia"][0]["md_file"]
    assert calls[0][2]["format"] == "json"
    calls.clear()
    assert await server.pl_search(source="saos", query="pytanie") == "Natywne wyszukiwanie bez modyfikacji"
    assert calls[0][2]["all"] == "pytanie"
    assert "format" not in calls[0][2]


def test_source_specific_cold_pdf_timeout(monkeypatch):
    monkeypatch.setenv("PRAWO_PL_MCP_TIMEOUT_LEGAL_CITE", "240")
    assert _timeout_for(SOURCES["legal-cite"]) == 240
    monkeypatch.delenv("PRAWO_PL_MCP_TIMEOUT_LEGAL_CITE")
    assert _timeout_for(SOURCES["saos"]) > 0


async def test_markdown_source_is_listed_without_spawning(store):
    catalog = json.loads(await server.pl_list_sources())
    byid = {item["id"]: item for item in catalog["sources"]}
    assert byid["md"]["runtime"] == "local:read-only"
    assert byid["legal-cite"]["native_params"]["pl_get_document"]["document_id"] == "citation"


@pytest.mark.parametrize("document_id,fragment,source,tool,args,status", [
    ("nsa:7E50984BB7", "Oryginalny fragment", "nsa", "get_judgment",
     {"doc_id": "7E50984BB7"}, "full"),
    ("kio:KIO 2924/21", "Oryginalny fragment", "kio", "kio_get_orzeczenie",
     {"signature_or_id": "KIO 2924/21"}, "full"),
    ("uodo:PublicDocument-123", "Oryginalny fragment", "uodo", "uodo_get_decision",
     {"id": "PublicDocument-123"}, "full"),
    ("eli:DU/2024/917", "art. 23 ustawy", "legal-cite", "verify_article",
     {"citation": "art. 23 DU/2024/917"}, "article_only"),
    ("eu-compliance:GDPR", "art. 33 rozporządzenia", "eu-compliance", "eu_article",
     {"regulation": "GDPR", "article_number": "33"}, "article_only"),
])
async def test_source_routes_are_explicit_and_retain_snippets(
        store, document_id, fragment, source, tool, args, status):
    item = hit(document_id)
    item["fragment"] = fragment
    requests = []

    async def invoke(s, t, a):
        requests.append((s, t, a))
        return "Treść pobrana z właściwego konektora. " * 25

    data = await hydrate.hydrate({"trafienia": [item]}, "pytanie", invoke)
    found = data["trafienia"][0]
    assert requests == [(source, tool, args)]
    assert found["fragment"] == fragment
    assert found["fulltext_status"] == status
    assert found["source_mcp"] == source
    assert (await md_store.read(found["md_file"], 1))["content_status"] == status


async def test_sn_exact_signature_pmi_result(store):
    item = hit("sn:iv-csk-192-19")
    item["tytul"] = "IV CSK 192/19"
    calls = []

    async def invoke(source, tool, args):
        calls.append((source, tool, args))
        return json.dumps({
            "signature": "IV CSK 192/19",
            "text": "Pełne uzasadnienie orzeczenia Sądu Najwyższego. " * 50,
            "source_url": "https://prawmi.pl/orzeczenie/iv-csk-192-19",
        })

    data = await hydrate.hydrate({"trafienia": [item]}, "x", invoke)
    assert calls == [("pmi", "pmi_get_document", {"document_id": "ruling:IV CSK 192/19"})]
    assert data["trafienia"][0]["fulltext_status"] == "full"


async def test_pmi_native_identifier_is_not_double_prefixed(store):
    item = hit("pmi:ruling:iv-csk-192-19")
    calls = []

    async def invoke(source, tool, args):
        calls.append((source, tool, args))
        return json.dumps({"kind": "ruling", "text": "Pobrana pełna treść dokumentu. " * 20})

    data = await hydrate.hydrate({"trafienia": [item]}, "x", invoke)
    assert calls == [("pmi", "pmi_get_document", {"document_id": "ruling:iv-csk-192-19"})]
    assert data["trafienia"][0]["fulltext_status"] == "full"


async def test_native_eureka_excerpt_never_labelled_full(store):
    item = hit("eureka:123")

    async def invoke(*_):
        raise AssertionError("Native get_interpretation is known to return an extract")

    data = await hydrate.hydrate({"trafienia": [item]}, "x", invoke)
    result = data["trafienia"][0]
    assert result["fulltext_status"] == "fragment_only"
    assert result["user_disclosure_required"]


async def test_explicit_unsupported_source_does_not_infer_pmi_identity(store):
    """An unknown source ID cannot be replaced by a PMI case-signature collision."""
    item = hit("unknown:151020250000503_I_C_000270_2015_Uz_2016-04-07_001")
    item["tytul"] = "I C 270/15"
    item["fragment"] = "Zachowany oryginalny fragment Repertorium."

    async def never(*_):
        raise AssertionError("Must not ask PMI for an unverified MS source ID")

    data = await hydrate.hydrate({"trafienia": [item]}, "I C 270/15", never)
    actual = data["trafienia"][0]
    assert actual["fulltext_status"] == "fragment_only"
    assert actual["fragment"] == item["fragment"]
    assert actual["user_disclosure_required"]
    assert "Unsupported source namespace" in actual["warning"]
    saved = await md_store.read(actual["md_file"], 1)
    assert saved["content_status"] == "fragment_only"



async def test_connector_error_does_not_discard_result(store):
    async def invoke(*_):
        return '{"isError":true,"error":"source rate limited"}'

    data = await hydrate.hydrate({"trafienia": [hit()]}, "x", invoke)
    result = data["trafienia"][0]
    assert result["fragment"] == hit()["fragment"]
    assert result["fulltext_status"] == "fragment_only"
    assert "source rate limited" in result["warning"]

async def test_saos_native_source_pagination_assembled_in_order():
    full = ("A" * 20_000) + ("B" * 63)
    calls = []

    async def invoke(source, tool, args):
        assert (source, tool) == ("saos", "get_judgment")
        calls.append(args)
        start = args["offset"]
        end = min(start + args["limit"], len(full))
        body = full[start:end]
        prefix = (f"=== ORZECZENIE SAOS ===\n\nID SAOS    : 316066\n\n"
                  f"--- Tresc (znaki {start}-{end} z {len(full)} lacznie) ---\n")
        suffix = (
            f"\n[...] Skrocono. Nastepny fragment: "
            f"get_judgment(id=316066, offset={end}, limit=2000). "
            "Pelna tresc: https://www.saos.org.pl/judgments/316066"
            if end < len(full) else ""
        )
        return prefix + body + suffix

    resolved = await hydrate._saos_full("316066", invoke)
    assert full in resolved
    assert "[...] Skrocono" not in resolved
    assert [c["offset"] for c in calls] == [0, 20_000]
    assert all(c["limit"] == 20_000 for c in calls)


async def test_saos_native_page_with_different_id_fails_closed():
    async def invoke(*_):
        return ("=== ORZECZENIE SAOS ===\n\nID SAOS    : 999\n\n"
                "--- Tresc (znaki 0-60 z 60 lacznie) ---\n" + "X" * 60)
    with pytest.raises(LookupError, match="did not match"):
        await hydrate._saos_full("316066", invoke)


async def test_saos_native_missing_continuation_fails_closed():
    async def invoke(*_):
        return ("=== ORZECZENIE SAOS ===\n\nID SAOS    : 316066\n\n"
                "--- Tresc (znaki 0-60 z 100 lacznie) ---\n" + "X" * 60)
    with pytest.raises(LookupError, match="continuation"):
        await hydrate._saos_full("316066", invoke)


async def test_saos_native_plain_text_without_identity_fails_closed():
    async def invoke(*_):
        return "A response that looks like full source text but lacks its own identifier. " * 2
    with pytest.raises(LookupError, match="verifiable judgment ID"):
        await hydrate._saos_full("316066", invoke)
