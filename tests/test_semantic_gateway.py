"""Repertorium-first gateway and existing remote MCP transport (offline)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import prawo_pl_mcp.pool as pool_mod
import prawo_pl_mcp.server as srv
from prawo_pl_mcp.registry import SOURCES
from prawo_pl_mcp.repertorium import parse_repertorium, source_for_ref


SAMPLE = '''Wyniki dla "art. 23 ustawy o ochronie zdrowia psychicznego" (jurysdykcja: pl)
Znaleziono: 3

- **Ustawa o ochronie zdrowia psychicznego (tekst jednolity, Dz.U. 2024 poz. 917)** (2024-06-21)
  document_id: eli:DU/2024/917
  fragment: "Art. 23.

### 1.

Osoba chora psychicznie może być przyjęta do szpitala"
  link: https://api.sejm.gov.pl/eli/acts/DU/2024/917

- **V CSK 145/14 (postanowienie SN)** (2014-08-06)
  document_id: saos:166511
  sad: Sąd Najwyższy
  fragment: "Uczestniczka postępowania"
  link: http://www.sn.pl/orzecznictwo/SitePages/Baza_orzeczen

- **I CSK 585/24 (postanowienie SN)** (2024-10-10)
  document_id: sn:K104SJcBZvGrB8P_h40G
  sad: Sąd Najwyższy - Izba Cywilna
  fragment: "dotychczasowe zachowanie"
  link: https://www.sn.pl/pl/wyszukiwarka-orzeczen
'''


def test_semantic_parser_follows_document_id_not_website_hostname():
    result = parse_repertorium(SAMPLE)
    assert result["total_reported"] == 3
    assert [x["document_ref"] for x in result["results"]] == [
        "eli:DU/2024/917", "saos:166511", "sn:K104SJcBZvGrB8P_h40G"
    ]
    assert result["results"][1]["backend"] == "saos"
    assert result["results"][1]["source_url"].startswith("http://www.sn.pl")
    assert result["results"][0]["fragment"].startswith("Art. 23.")
    assert result["results"][2]["direct_fetch_available"] is False


async def test_public_pl_find_always_calls_repertorium_first(monkeypatch):
    calls = []

    async def fake(source, tool, args):
        calls.append((source.id, tool, args))
        return SAMPLE

    monkeypatch.setattr(srv, "_proxy_call", fake)
    found = json.loads(await srv.pl_find("art. 23 ustawy", jurisdiction="pl"))
    assert calls == [("repertorium", "szukaj_repertorium", {
        "q": "art. 23 ustawy", "jurysdykcja": "pl",
    })]
    assert len(found["results"]) == 3


async def test_public_get_by_ref_routes_to_source_not_to_semantic_index(monkeypatch):
    calls = []

    async def fake(source, document_id, page=1):
        calls.append((source, document_id, page))
        return "SOURCE BODY"

    monkeypatch.setattr(srv, "pl_get_document", fake)
    assert await srv.pl_get_by_ref("saos:166511") == "SOURCE BODY"
    assert await srv.pl_get_by_ref("eli:DU/2024/917", page=2) == "SOURCE BODY"
    assert calls == [("saos", "166511", 1), ("isap", "DU/2024/917", 2)]


async def test_non_fetchable_sn_keeps_source_url_not_fake_saos_id():
    with pytest.raises(srv.PLLegalError) as err:
        await srv.pl_get_by_ref("sn:K104SJcBZvGrB8P_h40G")
    assert err.value.code == "source_unavailable"
    assert source_for_ref("sn:K104SJcBZvGrB8P_h40G") is None


def test_registry_reports_repertorium_as_remote_discovery_without_fake_get():
    entry = SOURCES["repertorium"]
    assert entry.runtime == "remote"
    assert entry.get is None


def test_repertorium_remote_transport_requires_config_no_spawn(monkeypatch):
    monkeypatch.delenv("PRAWO_PL_MCP_URL_REPERTORIUM", raising=False)
    with pytest.raises(pool_mod.SourceUnavailable, match="PRAWO_PL_MCP_URL_REPERTORIUM"):
        pool_mod._remote_transport(SOURCES["repertorium"])


async def test_configured_remote_uses_existing_service_instead_of_npx(monkeypatch):
    calls = []

    class Client:
        def __init__(self, transport, timeout):
            calls.append(("client", transport, timeout))
        async def __aenter__(self):
            calls.append(("connect",))
        async def __aexit__(self, *args):
            calls.append(("close",))
        def is_connected(self):
            return True

    monkeypatch.setenv("PRAWO_PL_MCP_URL_SAOS", "https://example.test/mcp")
    monkeypatch.setattr(pool_mod, "Client", Client)
    monkeypatch.setattr(pool_mod, "_spawn_spec", lambda *_: (_ for _ in ()).throw(
        AssertionError("Should never spawn a second copy")
    ))
    tmp = pool_mod.SourcePool()
    a = await tmp.get_client(SOURCES["saos"])
    b = await tmp.get_client(SOURCES["saos"])
    assert a is b
    assert len([x for x in calls if x[0] == "client"]) == 1
    await tmp.close_all()


def test_no_partial_cloudflare_service_credential(monkeypatch):
    monkeypatch.setenv("PRAWO_PL_MCP_URL_SAOS", "https://example.test/mcp")
    monkeypatch.setenv("PRAWO_PL_MCP_CF_CLIENT_ID_SAOS", "id")
    monkeypatch.delenv("PRAWO_PL_MCP_CF_CLIENT_SECRET_SAOS", raising=False)
    with pytest.raises(pool_mod.SourceUnavailable, match="Incomplete Cloudflare"):
        pool_mod._remote_transport(SOURCES["saos"])
