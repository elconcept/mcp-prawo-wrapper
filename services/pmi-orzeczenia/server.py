"""Public PrawMi HTML connector: rulings, statutes, article pages. No paid API."""
from __future__ import annotations

import asyncio
import difflib
import re
import time
import unicodedata
from typing import Any
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

BASE = "https://prawmi.pl"
INDEX_URL = BASE + "/ustawa"
RULING_BASE = BASE + "/orzeczenie/"
ACT_BASE = BASE + "/ustawa/"
USER_AGENT = "pmi-orzeczenia-personal-mcp/1.0"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html"}
ACT_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ARTICLE_ID = re.compile(r"^art-[0-9]+[a-z]?(?:-[a-z])?$")
RULING_SIG = re.compile(r"^[A-ZĄĆĘŁŃÓŚŹŻ0-9IVXLCM.\-\s]{1,18}\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]{1,8}\s+\d+/\d{2,4}$", re.I)
DZIENNIK = re.compile(r"(?:Dz\.?\s*U\.?\s*\d{4}\s*poz\.?\s*\d+)", re.I)
INDEX_TTL = 3600.0
_index_items: list[dict[str, str]] = []
_index_at = 0.0
_index_lock = asyncio.Lock()

mcp = FastMCP(
    "pmi-orzeczenia",
    instructions=(
        "Independent reader of public HTML at prawmi.pl. Free and without API keys. "
        "pmi_search searches the indexed titles of statutes and resolves exact ruling signatures. "
        "pmi_get_document fetches full text by ruling:<signature-or-slug>, act:<slug>, "
        "or article:<slug>:art-23. pmi_get_article reads one article. "
        "This connector is not a semantic search engine; use free Repertorium for semantic discovery. "
        "Article content omits AI analysis and site UI."
    ),
)

ALIASES = {
    "kpk": "kodeks-postepowania-karnego",
    "kk": "kodeks-karny",
    "kw": "kodeks-wykroczen",
    "kpc": "kodeks-postepowania-cywilnego",
    "kc": "kodeks-cywilny",
    "kpa": "kodeks-postepowania-administracyjnego",
    "ksh": "kodeks-spolek-handlowych",
    "kro": "kodeks-rodzinny-i-opiekunczy",
    "kkw": "kodeks-karny-wykonawczy",
    "kp": "kodeks-pracy",
}


def fold(value: str) -> str:
    value = value.lower().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def safe_slug(raw: str) -> str:
    value = unquote(raw).strip().lower()
    if not ACT_SLUG.fullmatch(value):
        raise ValueError("Invalid slug; only lowercase ASCII letters, digits and hyphens are supported.")
    return value


def ruling_slug(signature: str) -> str:
    value = fold(signature.strip())
    value = re.sub(r"^sygn(?:atura)?\.?\s*akt(?:a)?\.?\s*", "", value, flags=re.I)
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return safe_slug(value)


def article_id(raw: str) -> str:
    value = fold(raw.strip()).lower()
    value = re.sub(r"^art(?:\.|-)?\s*", "", value)
    value = value.replace(" ", "-").replace("_", "-")
    if not value.startswith("art-"):
        value = "art-" + value
    if not ARTICLE_ID.fullmatch(value):
        raise ValueError("Invalid article identifier. Examples: 23, art-23, 4a.")
    return value


async def fetch_html(url: str) -> BeautifulSoup:
    if not (url == INDEX_URL or url.startswith(ACT_BASE) or url.startswith(RULING_BASE)):
        raise ValueError("The URL is outside public PrawMi pages.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=False, headers=HEADERS) as client:
        response = await client.get(url)
    if response.status_code == 404:
        raise LookupError(f"Not found: {url}")
    if response.status_code != 200:
        raise RuntimeError(f"PrawMi HTTP {response.status_code}: {url}")
    if "text/html" not in response.headers.get("content-type", "").lower():
        raise RuntimeError("Unexpected response content type")
    return BeautifulSoup(response.text, "html.parser")


def clean_text(element: Any) -> str:
    value = element.get_text("\n", strip=True).replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


async def index_acts() -> list[dict[str, str]]:
    global _index_items, _index_at
    if _index_items and time.monotonic() - _index_at < INDEX_TTL:
        return _index_items
    async with _index_lock:
        if _index_items and time.monotonic() - _index_at < INDEX_TTL:
            return _index_items
        soup = await fetch_html(INDEX_URL)
        found: dict[str, dict[str, str]] = {}
        for section in soup.select("main section"):
            heading = section.find(["h2", "h3"])
            group = heading.get_text(" ", strip=True) if heading else "Inne"
            group = re.sub(r"\s*\(\s*\d+\s*\).*", "", group)
            for a in section.select('a[href^="/ustawa/"]'):
                path = a.get("href", "").split("?")[0].rstrip("/")
                slug = path[len("/ustawa/"):]
                if not ACT_SLUG.fullmatch(slug) or slug in found:
                    continue
                label = a.get_text(" ", strip=True)
                publication = DZIENNIK.search(label)
                title = label[:publication.start()].strip(" .") if publication else label
                found[slug] = {
                    "document_id": f"pmi:act:{slug}",
                    "title": title,
                    "publication": publication.group(0) if publication else "",
                    "slug": slug,
                    "category": group,
                    "source_url": BASE + path,
                }
        if not found:
            raise RuntimeError("PrawMi act index: no entries found (layout changed).")
        _index_items = list(found.values())
        _index_at = time.monotonic()
        return _index_items


async def get_ruling(signature: str) -> dict[str, Any]:
    slug = ruling_slug(signature)
    url = RULING_BASE + slug
    soup = await fetch_html(url)
    heading = soup.select_one("h1")
    if heading is None or ruling_slug(heading.get_text(" ", strip=True)) != slug:
        raise ValueError("PrawMi ruling heading does not match the requested signature.")
    section = soup.select("section#section-tresc .ruling-content")
    if len(section) != 1:
        raise RuntimeError("PrawMi ruling content selector changed.")
    content = clean_text(section[0])
    if len(content) < 50:
        raise RuntimeError("PrawMi ruling text is empty.")
    return {
        "document_id": f"pmi:ruling:{slug}",
        "kind": "ruling",
        "signature": heading.get_text(" ", strip=True),
        "source_url": url,
        "content_text": content,
        "total_chars": len(content),
    }


async def get_article(act: str, article: str) -> dict[str, Any]:
    slug = safe_slug(act)
    article = article_id(article)
    url = ACT_BASE + slug + "/" + article
    soup = await fetch_html(url)
    root = soup.select_one("article#przepis")
    if root is None:
        raise RuntimeError("PrawMi article container missing.")
    body = root.select_one("div.mt-6.space-y-5")
    if body is None:
        raise RuntimeError("PrawMi article text selector changed.")
    content = clean_text(body)
    if len(content) < 10:
        raise RuntimeError("PrawMi article text is empty.")
    act_title = root.select_one("p.text-sm")
    return {
        "document_id": f"pmi:article:{slug}:{article}",
        "kind": "article",
        "title": act_title.get_text(" ", strip=True) if act_title else slug,
        "article": article,
        "source_url": url,
        "content_text": f"{article.replace('art-', 'Art. ')}.\n{content}",
        "total_chars": len(content),
    }


async def get_act(slug: str) -> dict[str, Any]:
    slug = safe_slug(slug)
    url = ACT_BASE + slug
    soup = await fetch_html(url)
    heading = soup.select_one("main h1")
    articles = soup.select('main article[id^="art-"]')
    if not heading or not articles:
        raise RuntimeError("PrawMi act structure missing.")
    chunks = []
    for node in articles:
        art = node.get("id", "")
        if not ARTICLE_ID.fullmatch(art):
            continue
        children = [n for n in node.find_all(recursive=False) if getattr(n, "name", None)]
        body = children[-1] if len(children) >= 2 else node
        text = clean_text(body)
        if text:
            chunks.append(f"{art.replace('art-', 'Art. ')}.\n{text}")
    if not chunks:
        raise RuntimeError("PrawMi act articles have no text.")
    content = "\n\n".join(chunks)
    return {
        "document_id": f"pmi:act:{slug}",
        "kind": "act",
        "title": heading.get_text(" ", strip=True),
        "source_url": url,
        "article_count": len(chunks),
        "content_text": content,
        "total_chars": len(content),
    }


@mcp.tool
async def pmi_search(query: str, limit: int = 10, kind: str = "auto") -> dict[str, Any]:
    """Search the public law-title catalog, or resolve a known ruling signature.

    kind: auto / act / ruling. No site-wide semantic search is implied.
    Use free Repertorium MCP for semantic search of judgments.
    """
    if kind not in ("auto", "act", "ruling"):
        raise ValueError("kind must be auto, act, or ruling.")
    limit = max(1, min(30, int(limit)))
    query = query.strip()
    if not query:
        raise ValueError("query cannot be empty.")
    if kind in ("auto", "ruling") and RULING_SIG.fullmatch(query):
        try:
            r = await get_ruling(query)
        except LookupError:
            return {"query": query, "kind": "ruling", "count": 0, "results": []}
        return {"query": query, "kind": "ruling", "count": 1, "results": [
            {"document_id": r["document_id"], "title": r["signature"], "source_url": r["source_url"]}
        ]}
    if kind == "ruling":
        return {"query": query, "kind": "ruling", "count": 0, "results": [], "hint": "Search by case signature, or use free Repertorium."}

    docs = await index_acts()
    normalized = fold(query)
    alias = ALIASES.get(normalized)
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    matches: list[tuple[float, dict[str, str]]] = []
    for act in docs:
        title = fold(act["title"])
        slug = act["slug"]
        if alias == slug:
            score = 100.0
        elif normalized in title or normalized in slug:
            score = 30.0 + len(normalized) / max(1, len(title))
        else:
            title_tokens = set(re.findall(r"[a-z0-9]{3,}", title.replace("-", " ")))
            common = len(tokens & title_tokens)
            score = common * 2 / max(1, len(tokens)) + difflib.SequenceMatcher(None, normalized, title).ratio()
            if common == 0 and score < 0.65:
                continue
        matches.append((score, act))
    matches.sort(key=lambda pair: (-pair[0], pair[1]["title"]))
    return {"query": query, "kind": "act", "indexed": len(docs), "count": len(matches),
            "results": [act for _, act in matches[:limit]]}


@mcp.tool
async def pmi_get_document(document_id: str) -> dict[str, Any]:
    """Full text from public PrawMi HTML by ruling, act or article document ID.

    Accepts: ruling:XII Ko 26/23, act:kodeks-karny,
    article:ochronie-zdrowia-psychicznego:art-23.
    A leading pmi: prefix is optional.
    """
    value = document_id.strip()
    if value.startswith("pmi:"):
        value = value[4:]
    typ, sep, remainder = value.partition(":")
    if not sep:
        if RULING_SIG.fullmatch(value):
            return await get_ruling(value)
        raise ValueError("Specify ruling:<signature>, act:<slug>, or article:<slug>:<number>.")
    if typ == "ruling":
        return await get_ruling(remainder)
    if typ == "act":
        return await get_act(remainder)
    if typ == "article":
        slug, sep2, art = remainder.partition(":")
        if not sep2:
            raise ValueError("Article requires article:<act-slug>:art-<number>.")
        return await get_article(slug, art)
    raise ValueError("Unknown PrawMi document type.")


@mcp.tool
async def pmi_get_article(act_slug: str, article: str) -> dict[str, Any]:
    """Fetch one public statutory article, e.g. KPK art. 246 or mental-health act art. 23."""
    return await get_article(act_slug, article)


@mcp.tool
async def pmi_list_acts(query: str = "", limit: int = 100) -> dict[str, Any]:
    """Catalog of acts scraped from the public PrawMi /ustawa page (one index request per hour)."""
    if query:
        return await pmi_search(query, limit, kind="act")
    items = await index_acts()
    return {"indexed": len(items), "results": items[:max(1, min(100, limit))]}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
