"""Source routing and document-level merging without any network calls."""
import asyncio

from prawo_pl_mcp.case_law_federation import (
    CaseHit,
    SearchBatch,
    combine_hits,
    find_case_law,
)


def provider(name, hits=None, status="ok", seen=None, delay=0):
    async def invoke(query, case_number):
        if seen is not None:
            seen.append((name, query, case_number))
        if delay:
            await asyncio.sleep(delay)
        return SearchBatch(status=status, hits=list(hits or []))
    return invoke


def hit(source, ident, case="I C 2715/21", kind="wyrok z uzasadnieniem"):
    return CaseHit(
        source=source, source_id=ident, case_number=case,
        court="Sąd Okręgowy w Krakowie", judgment_date="2021-09-29",
        document_type=kind, url=f"https://example.org/{source}/{ident}",
    )


async def test_semantic_hints_not_treated_as_authoritative_results():
    seen = []
    result = await find_case_law(
        "naruszenie dóbr osobistych",
        {
            "repertorium": provider("repertorium", [hit("repertorium", "fragment")], seen=seen),
            "saos": provider("saos", [], status="empty", seen=seen),
            "nsa": provider("nsa", [], status="empty", seen=seen),
            "ms_cache": provider("ms_cache", [], status="empty", seen=seen),
            "ms_live": provider("ms_live", [], status="empty", seen=seen),
        },
    )
    assert result.status == "not_found_in_checked_sources"
    assert not result.records
    assert len(result.semantic_hints) == 1
    assert [x[0] for x in seen] == [
        "repertorium", "saos", "nsa", "ms_cache", "ms_live"
    ]


async def test_repertorium_timeout_does_not_block_source_search():
    calls = []
    result = await find_case_law(
        "I C 2715/21",
        {
            "repertorium": provider("repertorium", delay=0.05),
            "saos": provider("saos", [hit("saos", "123")], seen=calls),
            "ms_cache": provider("ms_cache", [], status="empty", seen=calls),
        },
        court_kind="common",
        semantic_timeout_s=0.001,
    )
    assert result.status == "found"
    assert result.records[0]["ref"] == "saos:123"
    assert result.checked["repertorium"] == "upstream_error"
    assert "ms_live" not in result.checked
    assert len(calls) == 2


async def test_strict_dedup_keeps_source_provenance():
    combined = combine_hits([hit("saos", "41"), hit("ms_cache", "MS-41")])
    assert len(combined) == 1
    assert len(combined[0]["sources"]) == 2
    assert combined[0]["ref"] == "saos:41"


async def test_same_signature_not_sufficient_to_merge_different_documents():
    combined = combine_hits([
        hit("saos", "41", kind="wyrok"),
        hit("ms_cache", "MS-41", kind="uzasadnienie"),
    ])
    assert len(combined) == 2


async def test_admin_route_skips_saos_and_common_court_portal():
    calls = []
    result = await find_case_law(
        "skarga na UODO",
        {"nsa": provider("nsa", [hit("nsa", "7E50984BB7")], seen=calls)},
        court_kind="administrative",
    )
    assert result.status == "found"
    assert set(result.checked) == {"nsa"}
    assert len(calls) == 1


async def test_ms_live_fallback_after_saos_nsa_ms_cache_misses():
    seen = []
    result = await find_case_law(
        "I C 2715/21",
        {
            name: provider(name, [hit("ms_live", "MS-1")] if name == "ms_live" else [],
                           status="ok" if name == "ms_live" else "empty", seen=seen)
            for name in ("saos", "nsa", "ms_cache", "ms_live")
        },
    )
    assert [call[0] for call in seen] == ["saos", "nsa", "ms_cache", "ms_live"]
    assert result.status == "found"
    assert result.records[0]["ref"] == "ms_live:MS-1"


async def test_unavailable_source_not_reported_as_verified_empty():
    result = await find_case_law(
        "I C 2715/21",
        {
            "saos": provider("saos", [], status="upstream_error"),
            "nsa": provider("nsa", [], status="empty"),
            "ms_cache": provider("ms_cache", [], status="empty"),
            "ms_live": provider("ms_live", [], status="empty"),
        },
    )
    assert result.status == "partial"
    assert result.checked["saos"] == "upstream_error"


async def test_live_ms_is_opt_in_when_existing_sources_have_hits():
    seen = []
    adapters = {
        "saos": provider("saos", [hit("saos", "41")], seen=seen),
        "nsa": provider("nsa", [], status="empty", seen=seen),
        "ms_cache": provider("ms_cache", [], status="empty", seen=seen),
        "ms_live": provider("ms_live", [hit("ms_live", "MS-41")], seen=seen),
    }
    normal = await find_case_law("I C 2715/21", adapters)
    assert normal.status == "found"
    assert "ms_live" not in [x[0] for x in seen]
    deep = await find_case_law("I C 2715/21", adapters, deep=True)
    assert len(deep.records) == 1
    assert "ms_live" in [x[0] for x in seen]
