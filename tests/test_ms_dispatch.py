"""Contract tests for ms: routing without accessing the network."""
from __future__ import annotations

import json

import pytest

import prawo_pl_mcp.hydrate as hydrate
import prawo_pl_mcp.server as srv
from prawo_pl_mcp.registry import SOURCES

DOC = "151020250000503_I_C_000270_2015_Uz_2016-04-07_001"


def response(signature="I C 270/15", identity_verified=True):
    return json.dumps({
        "document_id": "ms:" + DOC,
        "signature": signature,
        "date": "2016-01-19",
        "source_url": "https://orzeczenia.ms.gov.pl/content/$N/" + DOC,
        "content_text": "Sygn. akt: " + signature + "\n" + "UZASADNIENIE. " * 900,
        "content_status": "full",
        "identity_verified": identity_verified,
    }, ensure_ascii=False)


class CapturePool:
    def __init__(self):
        self.calls = []

    async def call(self, source, tool, arguments):
        self.calls.append((source.id, tool, arguments))
        return response()


async def test_ms_is_a_separate_registered_connector():
    ms = SOURCES["ms"]
    assert ms.runtime == "http"
    assert ms.get.tool == "ms_get_document"
    assert ms.search is None


async def test_auto_dispatch_to_official_ms_and_paginate(monkeypatch):
    pool = CapturePool()
    monkeypatch.setattr(srv, "POOL", pool)
    first = json.loads(await srv.pl_get_document("auto", "ms:" + DOC, page=1))
    third = json.loads(await srv.pl_get_document("auto", "ms:" + DOC, page=3))
    assert first["source"] == "ms"
    assert first["document_id"] == "ms:" + DOC
    assert first["pagination"] == "aggregator"
    assert first["total_pages"] >= 3
    assert third["page"] == 3
    assert pool.calls[0] == ("ms", "ms_get_document", {"document_id": DOC})


async def test_repertorium_hydrates_exact_ms_id():
    async def invoke(source, tool, arguments):
        assert (source, tool, arguments) == ("ms", "ms_get_document", {"document_id": DOC})
        return response()

    hit = {"document_id": "ms:" + DOC, "tytul": "I C 270/15 wyrok", "data": "2016-01-19"}
    content, status, mcp, tool, selector = await hydrate.resolve(hit, "", invoke)
    assert len(content) > 1000
    assert (status, mcp, tool, selector) == ("full", "ms", "ms_get_document", "")


@pytest.mark.parametrize("wrong", ["signature", "identity", "date"])
async def test_repertorium_rejects_wrong_ms_identity(wrong):
    async def invoke(source, tool, arguments):
        if wrong == "signature":
            return response(signature="I C 999/15")
        if wrong == "identity":
            return response(identity_verified=False)
        doc = json.loads(response())
        doc["date"] = "2015-10-29"
        return json.dumps(doc)

    hit = {"document_id": "ms:" + DOC, "tytul": "I C 270/15 wyrok", "data": "2016-01-19"}
    with pytest.raises(LookupError):
        await hydrate.resolve(hit, "", invoke)
