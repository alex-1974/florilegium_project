#!/usr/bin/env python3
# literature_pipeline/scripts/step1_collect_verify_links.py
"""Focused literature crawler for PDF discovery and verification.

Phase-3 style expansion in a single script:
- query generation from terms/patterns/domains
- search caching
- frontier-based focused crawl with SQLite persistence
- semantic URL prioritization using domain, anchor, parent context, title, URL tokens
- direct PDF verification with HEAD/GET fallback and magic-bytes check
- HTML page following with PDF extraction
- CSV outputs for raw and verified links
- JSONL logs and summary JSON

Expected root layout (root = parent of this script's directory):
    literature_pipeline/
      config/
        queries.yaml
        domains.yaml
        keywords.yaml
        crawl.yaml
      scripts/
        step1_collect_verify_links.py
      cache/
      data/
      logs/
      seeds/   # optional

The script is intentionally self-contained and uses defaults when config files
are absent. That keeps the pipeline runnable from day one.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_QUERIES = {
    "terms": [
        "fachwerk",
        "hallenhaus",
        "hausforschung",
        "bauarchäologie",
        "timber frame",
        "timber-framed building",
        "vernacular architecture",
        "medieval house",
        "cruck house",
        "pan de bois",
    ],
    "patterns": [
        "{term} pdf",
        "{term} filetype:pdf",
        "{term} research pdf",
        "{term} dissertation pdf",
    ],
    "languages": ["de", "en", "fr"],
    "seed_csv": None,
    "max_queries": 80,
}

DEFAULT_DOMAINS = {
    "high_priority": [
        "historicengland.org.uk",
        "vernaculararchitecture.org",
        "denkmalpflege.lvr.de",
        "denkmalpflege-bw.de",
        ".ac.uk",
        ".edu",
        ".de",
    ],
    "medium_priority": [
        "archive.org",
        "academia.edu",
        "researchgate.net",
        ".org",
    ],
    "blocked": [
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "pinterest.com",
        "x.com",
        "twitter.com",
        "youtube.com",
        "tiktok.com",
    ],
}

DEFAULT_KEYWORDS = {
    "strong_terms": [
        "fachwerk",
        "hallenhaus",
        "hausforschung",
        "bauarchäologie",
        "timber frame",
        "timber-framed",
        "vernacular architecture",
        "medieval house",
        "cruck",
        "dendrochronology",
        "pan de bois",
        "colombage",
        "denkmal",
        "historic building",
    ],
    "pdf_terms": [
        "pdf",
        "download",
        "full text",
        "fulltext",
        "bericht",
        "report",
        "article",
        "dissertation",
        "publication",
        "open access",
        "volltext",
    ],
    "negative_terms": [
        "login",
        "signup",
        "register",
        "cart",
        "shop",
        "product",
        "wallpaper",
        "advert",
        "cookie",
        "tag",
        "author archive",
    ],
    "synonyms": {
        "fachwerk": ["timber frame", "timber-framed", "pan de bois", "colombage"],
        "hallenhaus": ["low german house", "hall house"],
        "hausforschung": ["vernacular architecture", "building archaeology"],
    },
}

DEFAULT_CRAWL = {
    "search_engine": "duckduckgo_html",
    "pause_seconds": 1.0,
    "timeout_seconds": 20,
    "retries": 3,
    "max_depth": 2,
    "max_frontier_size": 5000,
    "max_pages_per_domain": 50,
    "max_pages_total": 500,
    "max_search_results_per_query": 30,
    "max_html_pages_to_follow_per_query": 10,
    "follow_html_pages": True,
    "follow_only_high_scoring_html": True,
    "min_follow_score": 20.0,
    "min_verify_score": 10.0,
    "verify_pdf_magic_bytes": True,
    "use_search_cache": True,
    "use_http_cache": True,
    "user_agent": "LiteraturePipelineBot/0.3 (+research focused PDF crawler)",
}

SEARCH_URL = "https://html.duckduckgo.com/html/"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FrontierItem:
    url: str
    normalized_url: str
    score: float
    depth: int
    source_url: str | None
    discovery_method: str
    anchor_text: str
    parent_title: str
    parent_context: str
    domain: str


@dataclass(slots=True)
class VerificationRecord:
    url: str
    normalized_url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    content_length: int | None
    is_pdf: bool
    verified: bool
    reason: str
    cache_hit: bool
    checked_at: str


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


TOKEN_RE = re.compile(r"[\W_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.split(text.lower()) if t]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def read_yaml(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(default))
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = json.loads(json.dumps(default))
    deep_merge(merged, data)
    return merged


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v


def ensure_dirs(root: Path) -> None:
    for p in [
        root / "config",
        root / "cache" / "search",
        root / "cache" / "http",
        root / "cache" / "pages",
        root / "data",
        root / "logs",
        root / "seeds",
    ]:
        p.mkdir(parents=True, exist_ok=True)


def normalize_url(url: str) -> str:
    url = unescape(url.strip())
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    # drop fragments, sort query params for stability
    qsl = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = []
    for k in sorted(qsl.keys()):
        vals = qsl[k]
        for v in sorted(vals):
            sorted_query.append(f"{k}={v}")
    query = "&".join(sorted_query)
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def is_blocked_domain(domain: str, blocked: list[str]) -> bool:
    return any(domain == b or domain.endswith(b) for b in blocked)


def domain_bucket(domain: str, domains_cfg: dict[str, Any]) -> str:
    for item in domains_cfg.get("high_priority", []):
        if domain == item or domain.endswith(item):
            return "high"
    for item in domains_cfg.get("medium_priority", []):
        if domain == item or domain.endswith(item):
            return "medium"
    return "low"


def domain_score(domain: str, domains_cfg: dict[str, Any]) -> float:
    bucket = domain_bucket(domain, domains_cfg)
    if bucket == "high":
        return 40.0
    if bucket == "medium":
        return 20.0
    return 0.0


def contains_any_phrase(text: str, phrases: list[str]) -> int:
    lower = text.lower()
    return sum(1 for p in phrases if p.lower() in lower)


def snippet_around(text: str, needle: str, radius: int = 160) -> str:
    lower = text.lower()
    idx = lower.find(needle.lower())
    if idx < 0:
        return text[: radius * 2]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(needle) + radius)
    return text[start:end]


class Progress:
    def __init__(self, total: int, label: str) -> None:
        self.total = max(total, 1)
        self.label = label
        self.current = 0
        self.enabled = sys.stdout.isatty()

    def update(self, current: int | None = None, detail: str = "") -> None:
        if current is None:
            self.current += 1
        else:
            self.current = current
        if not self.enabled:
            return
        width = 28
        filled = int(width * self.current / self.total)
        bar = "#" * filled + "-" * (width - filled)
        msg = f"[{bar}] {self.current:>4}/{self.total:<4} {self.label}"
        if detail:
            msg += f" | {detail[:42]}"
        print("\r" + msg.ljust(100), end="", flush=True)
        if self.current >= self.total:
            print()


# ---------------------------------------------------------------------------
# SQLite frontier
# ---------------------------------------------------------------------------


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS frontier (
            normalized_url TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            score REAL NOT NULL,
            depth INTEGER NOT NULL,
            source_url TEXT,
            discovery_method TEXT NOT NULL,
            anchor_text TEXT,
            parent_title TEXT,
            parent_context TEXT,
            domain TEXT,
            state TEXT NOT NULL DEFAULT 'queued',
            visited_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS page_log (
            normalized_url TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            domain TEXT,
            depth INTEGER,
            page_type TEXT,
            status TEXT,
            score REAL,
            title TEXT,
            visited_at TEXT,
            note TEXT
        )
        """
    )
    conn.commit()
    return conn


def frontier_count(conn: sqlite3.Connection, state: str = "queued") -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM frontier WHERE state=?", (state,)).fetchone()
    return int(row["c"])


def pages_count_for_domain(conn: sqlite3.Connection, domain: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM frontier WHERE domain=? AND state='visited'", (domain,)
    ).fetchone()
    return int(row["c"])


def push_frontier(conn: sqlite3.Connection, item: FrontierItem, max_frontier_size: int) -> bool:
    # keep best score if already known
    row = conn.execute(
        "SELECT score, state FROM frontier WHERE normalized_url=?", (item.normalized_url,)
    ).fetchone()
    now = utc_now_iso()
    if row is None:
        conn.execute(
            """
            INSERT INTO frontier (
                normalized_url, url, score, depth, source_url, discovery_method,
                anchor_text, parent_title, parent_context, domain, state,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (
                item.normalized_url,
                item.url,
                item.score,
                item.depth,
                item.source_url,
                item.discovery_method,
                item.anchor_text,
                item.parent_title,
                item.parent_context,
                item.domain,
                now,
                now,
            ),
        )
        conn.commit()
        trim_frontier(conn, max_frontier_size)
        return True
    if item.score > float(row["score"]) and row["state"] == "queued":
        conn.execute(
            """
            UPDATE frontier
            SET url=?, score=?, depth=?, source_url=?, discovery_method=?,
                anchor_text=?, parent_title=?, parent_context=?, domain=?, updated_at=?
            WHERE normalized_url=?
            """,
            (
                item.url,
                item.score,
                item.depth,
                item.source_url,
                item.discovery_method,
                item.anchor_text,
                item.parent_title,
                item.parent_context,
                item.domain,
                now,
                item.normalized_url,
            ),
        )
        conn.commit()
        return True
    return False


def trim_frontier(conn: sqlite3.Connection, max_frontier_size: int) -> None:
    count = frontier_count(conn, "queued")
    if count <= max_frontier_size:
        return
    overflow = count - max_frontier_size
    conn.execute(
        """
        DELETE FROM frontier
        WHERE normalized_url IN (
            SELECT normalized_url
            FROM frontier
            WHERE state='queued'
            ORDER BY score ASC, created_at ASC
            LIMIT ?
        )
        """,
        (overflow,),
    )
    conn.commit()


def pop_frontier(conn: sqlite3.Connection) -> FrontierItem | None:
    row = conn.execute(
        """
        SELECT * FROM frontier
        WHERE state='queued'
        ORDER BY score DESC, created_at ASC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    conn.execute(
        "UPDATE frontier SET state='visiting', updated_at=? WHERE normalized_url=?",
        (utc_now_iso(), row["normalized_url"]),
    )
    conn.commit()
    return FrontierItem(
        url=row["url"],
        normalized_url=row["normalized_url"],
        score=float(row["score"]),
        depth=int(row["depth"]),
        source_url=row["source_url"],
        discovery_method=row["discovery_method"],
        anchor_text=row["anchor_text"] or "",
        parent_title=row["parent_title"] or "",
        parent_context=row["parent_context"] or "",
        domain=row["domain"] or "",
    )


def mark_frontier(conn: sqlite3.Connection, normalized_url: str, state: str) -> None:
    conn.execute(
        "UPDATE frontier SET state=?, visited_at=?, updated_at=? WHERE normalized_url=?",
        (state, utc_now_iso(), utc_now_iso(), normalized_url),
    )
    conn.commit()


def log_page(
    conn: sqlite3.Connection,
    item: FrontierItem,
    page_type: str,
    status: str,
    title: str = "",
    note: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO page_log (
            normalized_url, url, domain, depth, page_type, status,
            score, title, visited_at, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_url) DO UPDATE SET
            page_type=excluded.page_type,
            status=excluded.status,
            score=excluded.score,
            title=excluded.title,
            visited_at=excluded.visited_at,
            note=excluded.note
        """,
        (
            item.normalized_url,
            item.url,
            item.domain,
            item.depth,
            page_type,
            status,
            item.score,
            title,
            utc_now_iso(),
            note,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def requests_session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    timeout: int,
    retries: int,
    **kwargs: Any,
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.request(method, url, timeout=timeout, allow_redirects=True, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:  # pragma: no cover - runtime resilience
            last_exc = exc
            time.sleep(min(8.0, 2.0**attempt))
    assert last_exc is not None
    raise last_exc


def search_cache_path(root: Path, query: str) -> Path:
    return root / "cache" / "search" / f"{sha256_text(query)}.html"


def page_cache_path(root: Path, url: str) -> Path:
    return root / "cache" / "pages" / f"{sha256_text(url)}.html"


def http_cache_path(root: Path, normalized_url: str) -> Path:
    return root / "cache" / "http" / f"{sha256_text(normalized_url)}.json"


# ---------------------------------------------------------------------------
# Search discovery
# ---------------------------------------------------------------------------


def build_queries(queries_cfg: dict[str, Any], domains_cfg: dict[str, Any]) -> list[str]:
    terms = list(dict.fromkeys(queries_cfg.get("terms", [])))
    patterns = list(dict.fromkeys(queries_cfg.get("patterns", [])))
    max_queries = int(queries_cfg.get("max_queries", 80))
    query_list: list[str] = []
    for term in terms:
        for pattern in patterns:
            query_list.append(pattern.format(term=term))
    # domain expansion for high-priority domains only; keeps search focused
    for term in terms:
        for dom in domains_cfg.get("high_priority", [])[:8]:
            query_list.append(f"site:{dom} {term} pdf")
            query_list.append(f"site:{dom} {term}")
    # de-duplicate while preserving order
    query_list = list(dict.fromkeys(query_list))
    return query_list[:max_queries]


def fetch_search_html(
    session: requests.Session,
    root: Path,
    query: str,
    crawl_cfg: dict[str, Any],
) -> tuple[str, bool]:
    cache_path = search_cache_path(root, query)
    if crawl_cfg.get("use_search_cache", True) and cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="ignore"), True
    response = request_with_retry(
        session,
        "POST",
        SEARCH_URL,
        timeout=int(crawl_cfg["timeout_seconds"]),
        retries=int(crawl_cfg["retries"]),
        data={"q": query},
    )
    cache_path.write_text(response.text, encoding="utf-8")
    time.sleep(float(crawl_cfg["pause_seconds"]))
    return response.text, False


def parse_duckduckgo_results(html: str, max_results: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        title = " ".join(a.get_text(" ", strip=True).split())
        if not href:
            continue
        url = extract_real_search_url(href)
        if not url:
            continue
        norm = normalize_url(url)
        if norm in seen:
            continue
        seen.add(norm)
        results.append({"url": url, "title": title})
        if len(results) >= max_results:
            break
    return results


def extract_real_search_url(href: str) -> str | None:
    href = unescape(href).strip()
    parsed = urlparse(href)
    if parsed.scheme in {"http", "https"}:
        return href
    if href.startswith("/l/"):
        full = urljoin(SEARCH_URL, href)
        qs = parse_qs(urlparse(full).query)
        uddg = qs.get("uddg")
        if uddg:
            return unquote(uddg[0])
    return None


# ---------------------------------------------------------------------------
# Semantic scoring
# ---------------------------------------------------------------------------


def score_candidate(
    url: str,
    domain: str,
    anchor_text: str,
    parent_title: str,
    parent_context: str,
    depth: int,
    domains_cfg: dict[str, Any],
    keywords_cfg: dict[str, Any],
) -> float:
    score = 0.0
    score += domain_score(domain, domains_cfg)

    if ".pdf" in url.lower():
        score += 35.0
    if any(tok in url.lower() for tok in ["download", "bitstream", "fulltext", "full-text"]):
        score += 10.0

    strong_terms = keywords_cfg.get("strong_terms", [])
    pdf_terms = keywords_cfg.get("pdf_terms", [])
    negative_terms = keywords_cfg.get("negative_terms", [])

    anchor_lower = anchor_text.lower()
    title_lower = parent_title.lower()
    context_lower = parent_context.lower()
    url_lower = url.lower()

    score += 8.0 * contains_any_phrase(anchor_lower, strong_terms)
    score += 5.0 * contains_any_phrase(anchor_lower, pdf_terms)
    score += 4.0 * contains_any_phrase(title_lower, strong_terms)
    score += 3.0 * contains_any_phrase(context_lower, strong_terms)
    score += 1.5 * contains_any_phrase(url_lower, strong_terms)
    score += 2.0 * contains_any_phrase(url_lower, pdf_terms)

    score -= 10.0 * contains_any_phrase(anchor_lower, negative_terms)
    score -= 10.0 * contains_any_phrase(url_lower, negative_terms)
    score -= 5.0 * max(depth - 1, 0)

    if anchor_text and re.search(r"\b(pdf|download|full text|volltext)\b", anchor_lower):
        score += 15.0

    return score


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


def load_seed_candidates(root: Path, seed_csv: str | None) -> list[str]:
    if not seed_csv:
        return []
    path = (root / seed_csv).resolve() if not Path(seed_csv).is_absolute() else Path(seed_csv)
    if not path.exists():
        print(f"Seed CSV not found: {path}")
        return []
    urls: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or row.get("link") or "").strip()
            if url:
                urls.append(url)
    print(f"Loaded {len(urls)} seed candidates from {path}")
    return urls


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_pdf_candidate(
    session: requests.Session,
    root: Path,
    url: str,
    crawl_cfg: dict[str, Any],
) -> VerificationRecord:
    normalized = normalize_url(url)
    cache_path = http_cache_path(root, normalized)
    if crawl_cfg.get("use_http_cache", True) and cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        data["cache_hit"] = True
        return VerificationRecord(**data)

    final_url = url
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    reason = "unknown"
    is_pdf = False

    # HEAD first, GET fallback for servers that do not provide useful HEAD data
    try:
        resp = request_with_retry(
            session,
            "HEAD",
            url,
            timeout=int(crawl_cfg["timeout_seconds"]),
            retries=int(crawl_cfg["retries"]),
        )
        final_url = resp.url
        status_code = resp.status_code
        content_type = resp.headers.get("content-type")
        content_length_raw = resp.headers.get("content-length")
        content_length = int(content_length_raw) if content_length_raw and content_length_raw.isdigit() else None
        if content_type and "pdf" in content_type.lower():
            is_pdf = True
            reason = "content_type_pdf"
    except Exception:
        pass

    if not is_pdf:
        try:
            resp = request_with_retry(
                session,
                "GET",
                url,
                timeout=int(crawl_cfg["timeout_seconds"]),
                retries=int(crawl_cfg["retries"]),
                stream=True,
            )
            final_url = resp.url
            status_code = resp.status_code
            content_type = resp.headers.get("content-type")
            content_length_raw = resp.headers.get("content-length")
            content_length = int(content_length_raw) if content_length_raw and content_length_raw.isdigit() else None
            chunk = next(resp.iter_content(8), b"")
            if content_type and "pdf" in content_type.lower():
                is_pdf = True
                reason = "content_type_pdf_get"
            if crawl_cfg.get("verify_pdf_magic_bytes", True) and chunk.startswith(b"%PDF-"):
                is_pdf = True
                reason = "magic_bytes_pdf"
        except Exception as exc:
            reason = f"request_failed:{type(exc).__name__}"

    record = VerificationRecord(
        url=url,
        normalized_url=normalized,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        content_length=content_length,
        is_pdf=is_pdf,
        verified=is_pdf,
        reason=reason,
        cache_hit=False,
        checked_at=utc_now_iso(),
    )
    cache_path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
    return record


# ---------------------------------------------------------------------------
# HTML crawling
# ---------------------------------------------------------------------------


def fetch_html_page(
    session: requests.Session,
    root: Path,
    url: str,
    crawl_cfg: dict[str, Any],
) -> tuple[str, bool]:
    cache_path = page_cache_path(root, normalize_url(url))
    if crawl_cfg.get("use_search_cache", True) and cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="ignore"), True
    response = request_with_retry(
        session,
        "GET",
        url,
        timeout=int(crawl_cfg["timeout_seconds"]),
        retries=int(crawl_cfg["retries"]),
    )
    text = response.text
    cache_path.write_text(text, encoding="utf-8")
    time.sleep(float(crawl_cfg["pause_seconds"]))
    return text, False


def extract_links_from_html(base_url: str, html: str) -> tuple[str, list[dict[str, str]]]:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())

    links: list[dict[str, str]] = []
    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        abs_url = urljoin(base_url, href)
        anchor = " ".join(a.get_text(" ", strip=True).split())
        # approximate local context via surrounding text of parent element
        parent_text = ""
        if a.parent:
            parent_text = " ".join(a.parent.get_text(" ", strip=True).split())
        context = snippet_around(parent_text, anchor) if anchor else parent_text[:320]
        links.append(
            {
                "url": abs_url,
                "anchor_text": anchor,
                "context": context,
                "title": title,
            }
        )
    return title, links


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main() -> int:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent
    ensure_dirs(root)

    queries_cfg = read_yaml(root / "config" / "queries.yaml", DEFAULT_QUERIES)
    domains_cfg = read_yaml(root / "config" / "domains.yaml", DEFAULT_DOMAINS)
    keywords_cfg = read_yaml(root / "config" / "keywords.yaml", DEFAULT_KEYWORDS)
    crawl_cfg = read_yaml(root / "config" / "crawl.yaml", DEFAULT_CRAWL)

    print(f"Pipeline root: {root}")

    session = requests_session(str(crawl_cfg["user_agent"]))
    db = open_db(root / "cache" / "frontier.sqlite")

    queries = build_queries(queries_cfg, domains_cfg)
    seeds = load_seed_candidates(root, queries_cfg.get("seed_csv"))

    stats: Counter[str] = Counter()
    stats["queries"] = len(queries)
    errors: list[str] = []

    # ------------------------------------------------------------------
    # Stage 1: search discovery
    # ------------------------------------------------------------------
    print("\nSEARCH")
    p_search = Progress(len(queries), "search")
    search_hits: list[dict[str, Any]] = []
    for idx, query in enumerate(queries, start=1):
        p_search.update(idx, query)
        try:
            html, cache_hit = fetch_search_html(session, root, query, crawl_cfg)
            if cache_hit:
                stats["search_cache_hits"] += 1
            results = parse_duckduckgo_results(html, int(crawl_cfg["max_search_results_per_query"]))
            for res in results:
                domain = url_domain(res["url"])
                if is_blocked_domain(domain, domains_cfg.get("blocked", [])):
                    continue
                score = score_candidate(
                    url=res["url"],
                    domain=domain,
                    anchor_text=res["title"],
                    parent_title="",
                    parent_context=query,
                    depth=0,
                    domains_cfg=domains_cfg,
                    keywords_cfg=keywords_cfg,
                )
                search_hits.append(
                    {
                        "query": query,
                        "title": res["title"],
                        "url": res["url"],
                        "source_domain": domain,
                        "score": round(score, 2),
                        "discovery_method": "search_result",
                    }
                )
                push_frontier(
                    db,
                    FrontierItem(
                        url=res["url"],
                        normalized_url=normalize_url(res["url"]),
                        score=score,
                        depth=0,
                        source_url=None,
                        discovery_method="search_result",
                        anchor_text=res["title"],
                        parent_title="",
                        parent_context=query,
                        domain=domain,
                    ),
                    int(crawl_cfg["max_frontier_size"]),
                )
            stats["search_hits"] += len(results)
        except Exception as exc:  # pragma: no cover - runtime resilience
            errors.append(f"search_failed::{query}::{type(exc).__name__}")

    # seeds enter frontier with medium-high base score
    for seed_url in seeds:
        domain = url_domain(seed_url)
        if is_blocked_domain(domain, domains_cfg.get("blocked", [])):
            continue
        seed_score = score_candidate(
            url=seed_url,
            domain=domain,
            anchor_text="seed",
            parent_title="seed",
            parent_context="seed",
            depth=0,
            domains_cfg=domains_cfg,
            keywords_cfg=keywords_cfg,
        ) + 10.0
        push_frontier(
            db,
            FrontierItem(
                url=seed_url,
                normalized_url=normalize_url(seed_url),
                score=seed_score,
                depth=0,
                source_url=None,
                discovery_method="seed",
                anchor_text="seed",
                parent_title="seed",
                parent_context="seed",
                domain=domain,
            ),
            int(crawl_cfg["max_frontier_size"]),
        )

    # ------------------------------------------------------------------
    # Stage 2: focused crawl frontier
    # ------------------------------------------------------------------
    print("\nCRAWL")
    total_budget = int(crawl_cfg["max_pages_total"])
    p_crawl = Progress(total_budget, "crawl")
    crawled = 0

    while crawled < total_budget:
        item = pop_frontier(db)
        if item is None:
            break
        crawled += 1
        p_crawl.update(crawled, f"{item.domain} {item.url[:28]}")

        if is_blocked_domain(item.domain, domains_cfg.get("blocked", [])):
            mark_frontier(db, item.normalized_url, "skipped")
            log_page(db, item, "blocked", "skipped", note="blocked_domain")
            continue

        if pages_count_for_domain(db, item.domain) >= int(crawl_cfg["max_pages_per_domain"]):
            mark_frontier(db, item.normalized_url, "skipped")
            log_page(db, item, "html", "skipped", note="domain_budget")
            continue

        # First, if score is high enough or url already looks like pdf: verify.
        should_verify = item.score >= float(crawl_cfg["min_verify_score"]) or ".pdf" in item.url.lower()
        if should_verify:
            record = verify_pdf_candidate(session, root, item.url, crawl_cfg)
            if record.cache_hit:
                stats["http_cache_hits"] += 1
            if record.verified:
                mark_frontier(db, item.normalized_url, "visited")
                log_page(db, item, "pdf", "verified", title=item.parent_title, note=record.reason)
                stats["verified_links"] += 1
                continue

        # If not a PDF and allowed to follow HTML pages, crawl HTML.
        if not crawl_cfg.get("follow_html_pages", True):
            mark_frontier(db, item.normalized_url, "visited")
            log_page(db, item, "non_pdf", "visited", note="follow_html_disabled")
            continue

        if crawl_cfg.get("follow_only_high_scoring_html", True) and item.score < float(crawl_cfg["min_follow_score"]):
            mark_frontier(db, item.normalized_url, "skipped")
            log_page(db, item, "html", "skipped", note="score_below_follow_threshold")
            continue

        if item.depth >= int(crawl_cfg["max_depth"]):
            mark_frontier(db, item.normalized_url, "skipped")
            log_page(db, item, "html", "skipped", note="max_depth")
            continue

        try:
            html, cache_hit = fetch_html_page(session, root, item.url, crawl_cfg)
            if cache_hit:
                stats["page_cache_hits"] += 1
            title, links = extract_links_from_html(item.url, html)
            mark_frontier(db, item.normalized_url, "visited")
            log_page(db, item, "html", "visited", title=title)
            stats["html_pages_visited"] += 1
            followed = 0
            for link in links:
                child_url = link["url"]
                child_domain = url_domain(child_url)
                if not child_domain or is_blocked_domain(child_domain, domains_cfg.get("blocked", [])):
                    continue
                child_score = score_candidate(
                    url=child_url,
                    domain=child_domain,
                    anchor_text=link["anchor_text"],
                    parent_title=link["title"],
                    parent_context=link["context"],
                    depth=item.depth + 1,
                    domains_cfg=domains_cfg,
                    keywords_cfg=keywords_cfg,
                )
                push_frontier(
                    db,
                    FrontierItem(
                        url=child_url,
                        normalized_url=normalize_url(child_url),
                        score=child_score,
                        depth=item.depth + 1,
                        source_url=item.url,
                        discovery_method="html_link",
                        anchor_text=link["anchor_text"],
                        parent_title=link["title"],
                        parent_context=link["context"],
                        domain=child_domain,
                    ),
                    int(crawl_cfg["max_frontier_size"]),
                )
                followed += 1
                # keep per-page expansion bounded
                if followed >= int(crawl_cfg["max_html_pages_to_follow_per_query"]):
                    break
        except Exception as exc:  # pragma: no cover - runtime resilience
            mark_frontier(db, item.normalized_url, "error")
            log_page(db, item, "html", "error", note=type(exc).__name__)
            errors.append(f"crawl_failed::{item.url}::{type(exc).__name__}")

    # ------------------------------------------------------------------
    # Exports
    # ------------------------------------------------------------------
    print("\nEXPORT")
    raw_rows = [dict(r) for r in db.execute("SELECT * FROM frontier ORDER BY score DESC, created_at ASC").fetchall()]

    verified_rows: list[dict[str, Any]] = []
    for path in sorted((root / "cache" / "http").glob("*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("verified"):
                verified_rows.append(row)
        except Exception:
            continue

    raw_csv = root / "data" / "links_raw.csv"
    verified_csv = root / "data" / "links_verified.csv"
    write_csv(raw_csv, raw_rows)
    write_csv(verified_csv, verified_rows)

    frontier_stats = {
        "queued": frontier_count(db, "queued"),
        "visited": frontier_count(db, "visited"),
        "skipped": frontier_count(db, "skipped"),
        "error": frontier_count(db, "error"),
        "visiting": frontier_count(db, "visiting"),
    }

    summary = {
        "generated_at": utc_now_iso(),
        "queries": len(queries),
        "seed_csv": queries_cfg.get("seed_csv"),
        "search_hits": int(stats.get("search_hits", 0)),
        "candidate_links": len(raw_rows),
        "verified_links": len(verified_rows),
        "search_cache_hits": int(stats.get("search_cache_hits", 0)),
        "http_cache_hits": int(stats.get("http_cache_hits", 0)),
        "page_cache_hits": int(stats.get("page_cache_hits", 0)),
        "html_pages_visited": int(stats.get("html_pages_visited", 0)),
        "frontier": frontier_stats,
        "errors": errors,
        "raw_csv": str(raw_csv.relative_to(root)),
        "verified_csv": str(verified_csv.relative_to(root)),
        "frontier_db": str((root / 'cache' / 'frontier.sqlite').relative_to(root)),
    }
    summary_path = root / "logs" / "step1_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
