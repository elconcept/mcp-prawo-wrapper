"""Exact MS judgment resolver backed by the official public ncourt XML API.

No signature-based search, Playwright, local corpus, or third-party mirror.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from fastmcp import FastMCP

API_BASE = "https://apiorzeczenia.wroclaw.sa.gov.pl/ncourt-api/judgement"
PUBLIC_BASE = "https://orzeczenia.ms.gov.pl/content/$N/"
MAX_XML_BYTES = 8_000_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{12,199}$")
SIGNATURE_PATTERN = re.compile(r"(?im)^\s*Sygn\.?\s*akt(?:a)?\s*:?\s*(\S[^\n]*)")
COURT_PATTERN = re.compile(r"(?im)^\s*(Sąd\s+(?:Rejonowy|Okręgowy|Apelacyjny)[^\n]*)")

mcp = FastMCP(
    "ms",
    instructions=(
        "Official Polish common-court judgment XML by exact source identifier. "
        "ms_get_document(document_id) accepts ms:<identifier> or bare identifier. "
        "It verifies the document ID and signature before returning complete text. "
        "It does not search by case signature."
    ),
)


def normalize_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("MS document ID must be text")
    native = value.strip().removeprefix("ms:")
    if not ID_PATTERN.fullmatch(native):
        raise ValueError("Invalid MS document identifier")
    return native


async def fetch_xml(client: httpx.AsyncClient, resource: str, native_id: str) -> ET.Element:
    if resource not in {"details", "content"}:
        raise ValueError("Unknown MS API resource")
    url = f"{API_BASE}/{resource}"
    response = await client.get(url, params={"id": native_id}, headers={"Accept": "text/xml"})
    if response.status_code == 404:
        raise LookupError(f"MS document not found: {native_id}")
    response.raise_for_status()
    if "xml" not in response.headers.get("content-type", "").lower():
        raise ValueError("MS API did not return XML")
    if len(response.content) > MAX_XML_BYTES:
        raise ValueError("MS XML exceeds size limit")
    if b"<!DOCTYPE" in response.content.upper() or b"<!ENTITY" in response.content.upper():
        raise ValueError("Unexpected XML entity declarations")
    try:
        return ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise ValueError("Malformed MS XML response") from exc


def checked_document(native_id: str, details: ET.Element, content: ET.Element) -> dict[str, Any]:
    if details.tag != "judgement" or details.get("id") != native_id:
        raise ValueError("MS metadata returned a different document ID")
    if content.tag != "xPart":
        raise ValueError("MS content was not an xPart judgment document")
    if content.get("xFlag") not in (None, "published"):
        raise ValueError("MS content is not marked published")

    signature = (details.findtext("signature") or "").strip()
    decision_date = (details.findtext("date") or "").strip()[:10]
    court_id = (details.findtext("courtId") or "").strip()
    department_id = (details.findtext("departmentId") or "").strip()
    if not signature or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", decision_date):
        raise ValueError("MS metadata is missing the case signature or judgment date")
    if court_id and department_id and native_id.startswith(court_id):
        stem = native_id.split("_", 1)[0]
        encoded_department = stem[len(court_id):]
        if not encoded_department.isdecimal() or int(encoded_department) != int(department_id):
            raise ValueError("MS source ID conflicts with court/department metadata")

    segments = [value.strip() for value in content.itertext() if value and value.strip()]
    body = "\n".join(segments)
    if len(body) < 100:
        raise ValueError("MS API returned an empty or incomplete judgment")
    found = SIGNATURE_PATTERN.search(body[:2500])
    if not found:
        raise ValueError("MS XML lacks a document signature")
    actual = found.group(1).strip()
    folded = lambda value: re.sub(r"\s+", "", value).casefold()
    if folded(actual) != folded(signature):
        raise ValueError(f"MS content signature '{actual}' differs from metadata '{signature}'")
    first_page = content.get("xFromPg")
    if first_page and first_page != "1":
        raise ValueError("MS API returned a partial page range")
    court = COURT_PATTERN.search(body[:3000])
    return {
        "document_id": "ms:" + native_id,
        "source": "ms",
        "source_url": PUBLIC_BASE + native_id,
        "source_api": API_BASE,
        "signature": signature,
        "date": decision_date,
        "court": court.group(1).strip() if court else None,
        "court_id": court_id or None,
        "department_id": department_id or None,
        "document_type": (details.findtext("type") or "").strip() or None,
        "content_text": body,
        "total_chars": len(body),
        "content_status": "full",
        "identity_verified": True,
        "complete": True,
    }


async def get_document(document_id: str) -> dict[str, Any]:
    native_id = normalize_id(document_id)
    async with httpx.AsyncClient(timeout=httpx.Timeout(45), follow_redirects=False) as client:
        details = await fetch_xml(client, "details", native_id)
        content = await fetch_xml(client, "content", native_id)
    return checked_document(native_id, details, content)


@mcp.tool
async def ms_get_document(document_id: str) -> dict[str, Any]:
    """Get the complete published judgment by its exact MS document ID."""
    return await get_document(document_id)


if __name__ == "__main__":
    mcp.run()
