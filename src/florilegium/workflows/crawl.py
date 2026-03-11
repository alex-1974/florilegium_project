#!/usr/bin/env python3
"""
Focused literature crawler for historical architecture / timber-frame research.

This crawler is designed for the BVILLAGE research pipeline and emphasizes:
- whole-page HTML classification
- section-aware link context
- robust PDF verification
- hybrid PDF scoring
- path semantics for download paths
- domain reputation / learning domain evaluation
- grep-friendly logs
- small crawl limits for analysis runs

Optional helper modules:
- crawler/scoring.py
- crawler/pdf_verify.py
- crawler/domain_reputation.py
- crawler/path_semantics.py

The script is intentionally self-contained and can fall back to internal
implementations when optional helper modules are not present.
"""

from __future__ import annotations

from florilegium.settings import get_paths, ensure_runtime_dirs

import argparse
import csv
import dataclasses
import html
import io
import json
import logging
import math
import mimetypes
import os
import queue
import re
import sys
import time
import traceback
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    import yaml  # optional
except Exception:
    yaml = None


# -----------------------------------------------------------------------------
# Optional external helpers
# -----------------------------------------------------------------------------

try:
    from florilegium.score.scoring import score_candidate as external_score_candidate  # type: ignore
except Exception:
    external_score_candidate = None

try:
    from florilegium.pdf.verify import verify_pdf_candidate as external_verify_pdf_candidate  # type: ignore
except Exception:
    external_verify_pdf_candidate = None

try:
    from florilegium.score.domain_reputation import DomainReputationStore as ExternalDomainReputationStore  # type: ignore
except Exception:
    ExternalDomainReputationStore = None

try:
    from florilegium.classify.path_semantics import analyze_path_semantics as external_analyze_path_semantics  # type: ignore
except Exception:
    external_analyze_path_semantics = None


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

USER_AGENT = (
    "BVILLAGE-LiteratureCrawler/1.0 "
    "(historical architecture research; contact: local-script)"
)

HTML_TIMEOUT = 15
PDF_TIMEOUT = 20
VERIFY_READ_BYTES = 64 * 1024
MAX_HTML_BYTES = 1_200_000

HTML_TYPES = (
    "text/html",
    "application/xhtml+xml",
)

PDF_TYPES = (
    "application/pdf",
    "application/x-pdf",
)

DEFAULT_HTML_CLASS_ORDER = (
    "publication",
    "repository",
    "heritage",
    "bibliography",
    "admin_legal",
    "teaching",
    "news",
    "navigation",
)

STOP_CLASSES = {"admin_legal", "news"}
SOFT_EXPAND_CLASSES = {"navigation", "bibliography", "repository", "heritage", "publication"}

POSITIVE_TERMS = {
    "historical": 1.1,
    "historic": 1.1,
    "architecture": 1.3,
    "vernacular": 1.4,
    "fachwerk": 1.6,
    "timber": 1.0,
    "framing": 1.0,
    "house": 0.5,
    "houses": 0.5,
    "hallenhaus": 1.8,
    "hall house": 1.7,
    "open hall": 1.7,
    "wealden": 1.8,
    "cruck": 1.8,
    "aisled": 1.8,
    "barn": 0.6,
    "bauforschung": 1.4,
    "denkmal": 1.2,
    "monument": 1.0,
    "heritage": 0.9,
    "medieval": 1.2,
    "middle ages": 1.2,
    "early modern": 1.1,
    "construction": 0.8,
    "joinery": 1.2,
    "carpentry": 1.0,
    "zimmermann": 1.2,
    "wood": 0.4,
    "oak": 0.3,
    "farmhouse": 0.8,
    "regionalgeschichte": 1.0,
    "hausforschung": 1.6,
    "dendro": 1.2,
    "tree-ring": 1.2,
    "timber-frame": 1.5,
    "timber frame": 1.5,
    "fachwerkhaus": 1.8,
}

NEGATIVE_TERMS = {
    "cookie": 1.0,
    "privacy": 0.8,
    "login": 1.0,
    "newsletter": 0.7,
    "jobs": 1.0,
    "shop": 0.9,
    "event": 0.5,
    "press release": 0.8,
    "press": 0.5,
    "donate": 0.8,
    "breaking news": 1.2,
    "sports": 1.2,
    "politics": 0.7,
    "weather": 1.2,
    "marketing": 1.0,
    "advertisement": 1.0,
}

SECTION_KIND_HINTS = {
    "references": "bibliography",
    "bibliography": "bibliography",
    "literature": "bibliography",
    "quellen": "bibliography",
    "links": "navigation",
    "further reading": "bibliography",
    "download": "repository",
    "downloads": "repository",
    "publications": "publication",
    "publikationen": "publication",
    "pdf": "repository",
    "sources": "bibliography",
    "archive": "repository",
    "digital collection": "repository",
}

RE_RELEVANT_TOPIC = re.compile(
    r"\b("
    r"fachwerk|fachwerkhaus|timber[- ]frame|vernacular|hallenhaus|hall house|wealden|"
    r"cruck|aisled|medieval|historic|historical architecture|bauforschung|hausforschung|"
    r"denkmal|monument|carpentry|joinery|wooden architecture|farmhouse|longhouse"
    r")\b",
    re.IGNORECASE,
)

RE_ADMIN = re.compile(
    r"\b(cookie|privacy|impressum|imprint|terms|conditions|policy|agb|kontakt|contact|"
    r"accessibility|barrierefreiheit|legal notice|copyright)\b",
    re.IGNORECASE,
)

RE_NEWS = re.compile(
    r"\b(news|latest|press|announcement|update|breaking|current events|blog)\b",
    re.IGNORECASE,
)

RE_TEACHING = re.compile(
    r"\b(course|teaching|seminar|lecture|student|worksheet|exercise|unterricht|school)\b",
    re.IGNORECASE,
)

RE_REPOSITORY = re.compile(
    r"\b(repository|archive|catalogue|catalog|database|record|viewer|collection|iiif|"
    r"document server|dspace|handle\.net|opac|findbuch|digital collections?)\b",
    re.IGNORECASE,
)

RE_PUBLICATION = re.compile(
    r"\b(publication|journal|article|paper|proceedings|thesis|dissertation|report|"
    r"monograph|buch|aufsatz|zeitschrift)\b",
    re.IGNORECASE,
)

RE_HERITAGE = re.compile(
    r"\b(heritage|denkmal|monument|listed building|inventar|denkmalliste|historic england|"
    r"cadw|dehio|unesco|bauaufnahme|bauforschung)\b",
    re.IGNORECASE,
)

RE_BIBLIO = re.compile(
    r"\b(bibliography|references|literature|works cited|further reading|quellen)\b",
    re.IGNORECASE,
)

RE_NAV = re.compile(
    r"\b(home|start|index|menu|navigation|browse|search results?|next|previous|contents?)\b",
    re.IGNORECASE,
)


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def safe_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = unquote(path)
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    # remove common tracking
    for key in list(query_params.keys()):
        if key.lower().startswith("utm_") or key.lower() in {
            "fbclid",
            "gclid",
            "mc_cid",
            "mc_eid",
            "ref",
            "source",
        }:
            query_params.pop(key, None)
    query_parts: list[str] = []
    for key in sorted(query_params):
        vals = sorted(query_params[key])
        for val in vals:
            query_parts.append(f"{quote(key)}={quote(val)}")
    query = "&".join(query_parts)
    fragment = ""
    return urlunparse((scheme, netloc, path, "", query, fragment))


def file_ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    suffix = Path(path).suffix.lower()
    return suffix


def is_probable_pdf_url(url: str) -> bool:
    ext = file_ext_from_url(url)
    if ext == ".pdf":
        return True
    low = url.lower()
    return (
        "pdf" in low
        and any(token in low for token in ("/download", "/document", "format=pdf", "view=pdf", "file="))
    )


def text_to_tokens(text: str) -> list[str]:
    text = html.unescape(text or "").lower()
    return re.findall(r"[a-zA-ZäöüÄÖÜß0-9][a-zA-ZäöüÄÖÜß0-9\-]{1,}", text)


def weighted_keyword_score(text: str) -> float:
    low = (text or "").lower()
    score = 0.0
    for term, weight in POSITIVE_TERMS.items():
        if term in low:
            score += weight
    for term, weight in NEGATIVE_TERMS.items():
        if term in low:
            score -= weight
    return score


def cosine_like_score(seed_terms: set[str], text: str) -> float:
    if not seed_terms:
        return 0.0
    tokens = text_to_tokens(text)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    overlap = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for term in seed_terms:
        a = 1.0
        b = float(counts.get(term, 0))
        overlap += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return overlap / math.sqrt(norm_a * norm_b)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def sniff_content_type(headers: Any) -> str:
    content_type = ""
    try:
        content_type = headers.get_content_type() or ""
    except Exception:
        pass
    if not content_type:
        try:
            content_type = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
        except Exception:
            content_type = ""
    return content_type.lower()


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

class TaggedLogger:
    def __init__(self, log_path: Path, verbose: bool = True) -> None:
        ensure_dir(log_path.parent)
        self.log_path = log_path
        self.verbose = verbose
        self._fh = log_path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._fh.close()

    def log(self, tag: str, **fields: Any) -> None:
        parts = [now_ts(), tag]
        for key, val in fields.items():
            sval = normalize_space(str(val))
            parts.append(f"{key}={sval}")
        line = " | ".join(parts)
        self._fh.write(line + "\n")
        self._fh.flush()
        if self.verbose:
            print(line)


# -----------------------------------------------------------------------------
# Domain reputation
# -----------------------------------------------------------------------------

@dataclass
class _DomainReputationState:
    html_seen: int = 0
    pdf_checked: int = 0
    verify_fail: int = 0
    decisions: Counter = field(default_factory=Counter)

    def reputation(self) -> float:
        good = (
            self.decisions.get("accept", 0) * 1.0
            + self.decisions.get("maybe", 0) * 0.4
            + self.decisions.get("review", 0) * 0.2
        )
        bad = (
            self.verify_fail * 0.7
            + self.decisions.get("reject", 0) * 0.8
            + self.decisions.get("skip", 0) * 0.2
        )
        exposure = self.html_seen * 0.05 + self.pdf_checked * 0.15
        return round(good - bad + exposure, 4)

    def success_rate(self) -> float:
        total = self.pdf_checked or 0
        if total <= 0:
            return 0.0
        accepted = self.decisions.get("accept", 0) + self.decisions.get("maybe", 0)
        return round(accepted / total, 4)


class LocalDomainReputationStore:
    def __init__(self) -> None:
        self._state: dict[str, _DomainReputationState] = defaultdict(_DomainReputationState)

    def note_html(self, domain: str) -> None:
        self._state[domain].html_seen += 1

    def note_pdf_checked(self, domain: str) -> None:
        self._state[domain].pdf_checked += 1

    def note_verify_fail(self, domain: str) -> None:
        self._state[domain].verify_fail += 1

    def note_decision(self, domain: str, decision: str) -> None:
        self._state[domain].decisions[decision] += 1

    def reputation(self, domain: str) -> float:
        return self._state[domain].reputation()

    def success_rate(self, domain: str) -> float:
        return self._state[domain].success_rate()

    def summary_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for domain in sorted(self._state):
            st = self._state[domain]
            rows.append(
                {
                    "domain": domain,
                    "html_seen": st.html_seen,
                    "pdf_checked": st.pdf_checked,
                    "verify_fail": st.verify_fail,
                    "accept": st.decisions.get("accept", 0),
                    "maybe": st.decisions.get("maybe", 0),
                    "review": st.decisions.get("review", 0),
                    "reject": st.decisions.get("reject", 0),
                    "skip": st.decisions.get("skip", 0),
                    "reputation": st.reputation(),
                    "success_rate": st.success_rate(),
                }
            )
        return rows


def build_domain_reputation_store() -> Any:
    if ExternalDomainReputationStore is not None:
        try:
            return ExternalDomainReputationStore()
        except Exception:
            pass
    return LocalDomainReputationStore()


# -----------------------------------------------------------------------------
# Path semantics
# -----------------------------------------------------------------------------

def local_analyze_path_semantics(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    path = unquote(parsed.path or "").lower()
    segments = [seg for seg in path.split("/") if seg]
    name = Path(path).name

    family = "generic"
    if any(seg in {"download", "downloads", "pdf", "docs", "document", "documents"} for seg in segments):
        family = "direct_download"
    elif any(seg in {"repository", "archive", "record", "item", "handle", "viewer"} for seg in segments):
        family = "repository_record"
    elif any(seg in {"bitstream", "content", "fileadmin", "media"} for seg in segments):
        family = "storage_blob"
    elif any(seg in {"wp-content", "uploads"} for seg in segments):
        family = "cms_upload"
    elif any(seg in {"assets", "static"} for seg in segments):
        family = "static_asset"

    prototype_scores = {
        "direct_download": 0.0,
        "repository_record": 0.0,
        "storage_blob": 0.0,
        "cms_upload": 0.0,
        "static_asset": 0.0,
        "generic": 0.0,
    }
    prototype_scores[family] = 1.0

    score = 0.0
    if family == "direct_download":
        score += 1.6
    elif family == "repository_record":
        score += 1.4
    elif family == "storage_blob":
        score += 1.0
    elif family == "cms_upload":
        score += 0.8
    elif family == "static_asset":
        score += 0.3

    if re.search(r"\b(pdf|paper|report|thesis|article|journal|monograph)\b", path):
        score += 1.2
    if re.search(r"\b(scan|flyer|poster|brochure|menu)\b", path):
        score -= 0.8
    if name.endswith(".pdf"):
        score += 0.8

    prototype_name = family
    return {
        "path_family": family,
        "prototype_name": prototype_name,
        "prototype_scores": json.dumps(prototype_scores, sort_keys=True),
        "path_score": round(score, 4),
    }


def analyze_path_semantics(url: str) -> dict[str, Any]:
    if external_analyze_path_semantics is not None:
        try:
            res = external_analyze_path_semantics(url)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    return local_analyze_path_semantics(url)


# -----------------------------------------------------------------------------
# PDF verification
# -----------------------------------------------------------------------------

@dataclass
class PdfVerifyResult:
    ok: bool
    reason: str
    final_url: str
    content_type: str = ""
    status_code: int | None = None
    content_length: int | None = None
    header_pdf: bool = False
    ext_pdf: bool = False
    first_bytes_pdf: bool = False


def local_verify_pdf_candidate(url: str, timeout: int = PDF_TIMEOUT) -> PdfVerifyResult:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            final_url = normalize_url(resp.geturl())
            content_type = sniff_content_type(resp.headers)
            content_length = None
            try:
                raw_len = resp.headers.get("Content-Length")
                if raw_len:
                    content_length = int(raw_len)
            except Exception:
                content_length = None

            first = resp.read(VERIFY_READ_BYTES)
            first_bytes_pdf = first.startswith(b"%PDF-")
            header_pdf = any(t in content_type for t in PDF_TYPES)
            ext_pdf = file_ext_from_url(final_url) == ".pdf" or file_ext_from_url(url) == ".pdf"

            if first_bytes_pdf or (header_pdf and ext_pdf):
                return PdfVerifyResult(
                    ok=True,
                    reason="pdf_verified",
                    final_url=final_url,
                    content_type=content_type,
                    status_code=getattr(resp, "status", None),
                    content_length=content_length,
                    header_pdf=header_pdf,
                    ext_pdf=ext_pdf,
                    first_bytes_pdf=first_bytes_pdf,
                )

            if header_pdf:
                # some servers omit %PDF at start due to wrapper / redirect artifact
                return PdfVerifyResult(
                    ok=True,
                    reason="header_pdf_only",
                    final_url=final_url,
                    content_type=content_type,
                    status_code=getattr(resp, "status", None),
                    content_length=content_length,
                    header_pdf=header_pdf,
                    ext_pdf=ext_pdf,
                    first_bytes_pdf=first_bytes_pdf,
                )

            return PdfVerifyResult(
                ok=False,
                reason=f"not_pdf content_type={content_type!r}",
                final_url=final_url,
                content_type=content_type,
                status_code=getattr(resp, "status", None),
                content_length=content_length,
                header_pdf=header_pdf,
                ext_pdf=ext_pdf,
                first_bytes_pdf=first_bytes_pdf,
            )
    except HTTPError as exc:
        return PdfVerifyResult(
            ok=False,
            reason=f"http_error {exc.code}",
            final_url=url,
            status_code=exc.code,
        )
    except URLError as exc:
        return PdfVerifyResult(
            ok=False,
            reason=f"url_error {exc.reason}",
            final_url=url,
        )
    except Exception as exc:
        return PdfVerifyResult(
            ok=False,
            reason=f"verify_exception {type(exc).__name__}: {exc}",
            final_url=url,
        )


def verify_pdf_candidate(url: str, timeout: int = PDF_TIMEOUT) -> PdfVerifyResult:
    if external_verify_pdf_candidate is not None:
        try:
            res = external_verify_pdf_candidate(url, timeout=timeout)
            if isinstance(res, PdfVerifyResult):
                return res
            if isinstance(res, dict):
                return PdfVerifyResult(
                    ok=bool(res.get("ok")),
                    reason=str(res.get("reason", "")),
                    final_url=str(res.get("final_url", url)),
                    content_type=str(res.get("content_type", "")),
                    status_code=res.get("status_code"),
                    content_length=res.get("content_length"),
                    header_pdf=bool(res.get("header_pdf", False)),
                    ext_pdf=bool(res.get("ext_pdf", False)),
                    first_bytes_pdf=bool(res.get("first_bytes_pdf", False)),
                )
        except Exception:
            pass
    return local_verify_pdf_candidate(url, timeout=timeout)


# -----------------------------------------------------------------------------
# Scoring
# -----------------------------------------------------------------------------

@dataclass
class ScoreResult:
    score: float
    cosine_score: float
    context_score: float
    url_score: float
    filename_score: float
    path_score: float
    domain_score: float
    repository_score: float
    scientific_score: float
    semantic_score: float
    spam_risk: float
    confidence: float
    decision: str
    reason: str


def local_score_candidate(
    *,
    url: str,
    anchor_text: str,
    surrounding_text: str,
    page_text: str,
    section_heading: str,
    section_kind: str,
    verify: PdfVerifyResult,
    seed_terms: set[str],
    domain_store: Any,
) -> ScoreResult:
    domain = safe_domain(url)
    parsed = analyze_path_semantics(url)

    url_text = " ".join(
        [
            urlparse(url).path.replace("/", " "),
            urlparse(url).query.replace("&", " "),
            anchor_text,
        ]
    )
    filename = Path(unquote(urlparse(url).path)).name

    cosine = round(cosine_like_score(seed_terms, " ".join([anchor_text, surrounding_text, page_text, url_text])), 4)
    context_score = round(
        0.30 * max(0.0, weighted_keyword_score(anchor_text))
        + 0.45 * max(0.0, weighted_keyword_score(surrounding_text))
        + 0.25 * max(0.0, weighted_keyword_score(section_heading)),
        4,
    )
    url_score = round(max(0.0, weighted_keyword_score(url_text)), 4)
    filename_score = round(max(0.0, weighted_keyword_score(filename)), 4)
    path_score = round(float(parsed.get("path_score", 0.0)), 4)

    domain_score = round(float(domain_store.reputation(domain)), 4)
    repository_score = 0.0
    if section_kind in {"repository", "bibliography", "publication"}:
        repository_score += 0.9
    if any(token in domain for token in ("doi.org", "handle.net", "jstor", "zenodo", "archaeologydataservice")):
        repository_score += 1.0
    if any(token in domain for token in ("gov", "ac.uk", "edu", "uni-", "univ", "museum", "heritage")):
        repository_score += 0.6
    repository_score = round(repository_score, 4)

    scientific_score = 0.0
    scientific_score += 1.2 if RE_PUBLICATION.search(page_text + " " + section_heading) else 0.0
    scientific_score += 0.8 if RE_BIBLIO.search(page_text + " " + section_heading) else 0.0
    scientific_score += 0.5 if re.search(r"\b(doi|isbn|issn|author|abstract|citation)\b", page_text, re.I) else 0.0
    scientific_score = round(scientific_score, 4)

    semantic_score = round(
        1.5 * cosine
        + 0.35 * context_score
        + 0.25 * url_score
        + 0.20 * filename_score
        + 0.30 * repository_score
        + 0.25 * scientific_score,
        4,
    )

    spam_risk = 0.0
    combined = " ".join([url, anchor_text, surrounding_text, page_text[:600]])
    if RE_ADMIN.search(combined):
        spam_risk += 0.8
    if RE_NEWS.search(combined):
        spam_risk += 0.3
    if re.search(r"\b(flyer|brochure|menu|newsletter|advert)\b", combined, re.I):
        spam_risk += 0.8
    if verify.content_length is not None and verify.content_length < 15_000:
        spam_risk += 0.5
    spam_risk = round(spam_risk, 4)

    score = round(
        2.0 * cosine
        + context_score
        + 0.6 * url_score
        + 0.5 * filename_score
        + 0.8 * path_score
        + 0.25 * max(domain_score, -1.0)
        + repository_score
        + scientific_score
        + semantic_score
        - 1.6 * spam_risk
        + (0.9 if verify.ok else -2.5),
        4,
    )

    confidence = round(
        min(
            1.0,
            max(
                0.0,
                0.20
                + 0.15 * min(cosine, 1.0)
                + 0.08 * min(context_score, 4.0)
                + 0.08 * min(repository_score, 2.0)
                + 0.12 * (1.0 if verify.ok else 0.0)
                - 0.10 * min(spam_risk, 2.0),
            ),
        ),
        4,
    )

    if not verify.ok:
        decision = "reject"
        reason = f"verify_fail:{verify.reason}"
    elif score >= 7.0 and confidence >= 0.45:
        decision = "accept"
        reason = "high_score"
    elif score >= 4.5:
        decision = "maybe"
        reason = "medium_score"
    elif score >= 2.5:
        decision = "review"
        reason = "needs_review"
    else:
        decision = "reject"
        reason = "low_score"

    return ScoreResult(
        score=score,
        cosine_score=cosine,
        context_score=context_score,
        url_score=url_score,
        filename_score=filename_score,
        path_score=path_score,
        domain_score=domain_score,
        repository_score=repository_score,
        scientific_score=scientific_score,
        semantic_score=semantic_score,
        spam_risk=spam_risk,
        confidence=confidence,
        decision=decision,
        reason=reason,
    )


def score_candidate(**kwargs: Any) -> ScoreResult:
    if external_score_candidate is not None:
        try:
            res = external_score_candidate(**kwargs)
            if isinstance(res, ScoreResult):
                return res
            if isinstance(res, dict):
                return ScoreResult(
                    score=float(res.get("score", 0.0)),
                    cosine_score=float(res.get("cosine_score", 0.0)),
                    context_score=float(res.get("context_score", 0.0)),
                    url_score=float(res.get("url_score", 0.0)),
                    filename_score=float(res.get("filename_score", 0.0)),
                    path_score=float(res.get("path_score", 0.0)),
                    domain_score=float(res.get("domain_score", 0.0)),
                    repository_score=float(res.get("repository_score", 0.0)),
                    scientific_score=float(res.get("scientific_score", 0.0)),
                    semantic_score=float(res.get("semantic_score", 0.0)),
                    spam_risk=float(res.get("spam_risk", 0.0)),
                    confidence=float(res.get("confidence", 0.0)),
                    decision=str(res.get("decision", "review")),
                    reason=str(res.get("reason", "")),
                )
        except Exception:
            pass
    return local_score_candidate(**kwargs)


# -----------------------------------------------------------------------------
# HTML parsing
# -----------------------------------------------------------------------------

@dataclass
class ParsedLink:
    url: str
    anchor_text: str
    section_heading: str
    section_kind: str
    surrounding_text: str
    rel: str = ""
    title: str = ""


@dataclass
class ParsedHtml:
    title: str
    meta_description: str
    text: str
    headings: list[tuple[str, str]]
    links: list[ParsedLink]
    lang: str = ""


class SectionAwareHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url

        self.title_text: list[str] = []
        self.meta_description = ""
        self.page_lang = ""

        self._in_title = False
        self._current_heading_tag = ""
        self._current_heading_text: list[str] = []
        self._current_heading = ""
        self._current_section_kind = "body"

        self._current_link_href = ""
        self._current_link_title = ""
        self._current_link_rel = ""
        self._current_link_text: list[str] = []

        self._recent_text_buffer: deque[str] = deque(maxlen=20)
        self._headings: list[tuple[str, str]] = []
        self._links: list[ParsedLink] = []
        self._all_text_chunks: list[str] = []

        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if tag == "html":
            self.page_lang = attrs_dict.get("lang", "") or attrs_dict.get("xml:lang", "")

        if tag == "title":
            self._in_title = True

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._current_heading_tag = tag
            self._current_heading_text = []

        if tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            if name == "description" or prop == "og:description":
                if not self.meta_description:
                    self.meta_description = normalize_space(attrs_dict.get("content", ""))

        if tag == "a":
            href = attrs_dict.get("href", "").strip()
            self._current_link_href = urljoin(self.base_url, href) if href else ""
            self._current_link_title = attrs_dict.get("title", "").strip()
            self._current_link_rel = attrs_dict.get("rel", "").strip()
            self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        if tag == "title":
            self._in_title = False

        if tag == self._current_heading_tag and self._current_heading_tag:
            heading_text = normalize_space(" ".join(self._current_heading_text))
            if heading_text:
                self._current_heading = heading_text
                self._current_section_kind = infer_section_kind(heading_text)
                self._headings.append((self._current_heading_tag, heading_text))
                self._all_text_chunks.append(heading_text)
                self._recent_text_buffer.append(heading_text)
            self._current_heading_tag = ""
            self._current_heading_text = []

        if tag == "a" and self._current_link_href:
            anchor_text = normalize_space(" ".join(self._current_link_text))
            surrounding_text = normalize_space(" ".join(self._recent_text_buffer))
            self._links.append(
                ParsedLink(
                    url=normalize_url(self._current_link_href),
                    anchor_text=anchor_text,
                    section_heading=self._current_heading,
                    section_kind=self._current_section_kind,
                    surrounding_text=surrounding_text,
                    rel=self._current_link_rel,
                    title=self._current_link_title,
                )
            )
            self._current_link_href = ""
            self._current_link_title = ""
            self._current_link_rel = ""
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = normalize_space(data)
        if not text:
            return

        if self._in_title:
            self.title_text.append(text)

        if self._current_heading_tag:
            self._current_heading_text.append(text)

        if self._current_link_href:
            self._current_link_text.append(text)

        self._all_text_chunks.append(text)
        self._recent_text_buffer.append(text)

    def parsed(self) -> ParsedHtml:
        return ParsedHtml(
            title=normalize_space(" ".join(self.title_text)),
            meta_description=self.meta_description,
            text=normalize_space(" ".join(self._all_text_chunks)),
            headings=list(self._headings),
            links=list(self._links),
            lang=self.page_lang,
        )


def infer_section_kind(heading: str) -> str:
    low = (heading or "").strip().lower()
    if not low:
        return "body"
    for key, val in SECTION_KIND_HINTS.items():
        if key in low:
            return val
    if RE_BIBLIO.search(low):
        return "bibliography"
    if RE_PUBLICATION.search(low):
        return "publication"
    if RE_REPOSITORY.search(low):
        return "repository"
    if RE_HERITAGE.search(low):
        return "heritage"
    if RE_NAV.search(low):
        return "navigation"
    return "body"


# -----------------------------------------------------------------------------
# HTML fetching / classification
# -----------------------------------------------------------------------------

@dataclass
class HtmlFetchResult:
    ok: bool
    url: str
    final_url: str
    status_code: int | None
    content_type: str
    html_text: str
    error: str = ""


def fetch_html(url: str, timeout: int = HTML_TIMEOUT) -> HtmlFetchResult:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            final_url = normalize_url(resp.geturl())
            content_type = sniff_content_type(resp.headers)
            raw = resp.read(MAX_HTML_BYTES)
            charset = getattr(resp.headers, "get_content_charset", lambda default=None: default)("utf-8") or "utf-8"
            try:
                text = raw.decode(charset, errors="replace")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            if content_type and content_type not in HTML_TYPES and "html" not in content_type:
                return HtmlFetchResult(
                    ok=False,
                    url=url,
                    final_url=final_url,
                    status_code=getattr(resp, "status", None),
                    content_type=content_type,
                    html_text="",
                    error=f"non_html:{content_type}",
                )
            return HtmlFetchResult(
                ok=True,
                url=url,
                final_url=final_url,
                status_code=getattr(resp, "status", None),
                content_type=content_type,
                html_text=text,
            )
    except HTTPError as exc:
        return HtmlFetchResult(
            ok=False,
            url=url,
            final_url=url,
            status_code=exc.code,
            content_type="",
            html_text="",
            error=f"http_error:{exc.code}",
        )
    except URLError as exc:
        return HtmlFetchResult(
            ok=False,
            url=url,
            final_url=url,
            status_code=None,
            content_type="",
            html_text="",
            error=f"url_error:{exc.reason}",
        )
    except Exception as exc:
        return HtmlFetchResult(
            ok=False,
            url=url,
            final_url=url,
            status_code=None,
            content_type="",
            html_text="",
            error=f"fetch_exception:{type(exc).__name__}:{exc}",
        )


@dataclass
class HtmlDecision:
    url: str
    final_url: str
    page_type: str
    class_scores: dict[str, float]
    relevance_score: float
    expand: bool
    reason: str
    title: str
    lang: str
    link_count: int


def classify_html_page(url: str, parsed: ParsedHtml, seed_terms: set[str]) -> HtmlDecision:
    title = parsed.title
    text = " ".join([parsed.title, parsed.meta_description, parsed.text[:5000]])
    low = text.lower()

    class_scores: dict[str, float] = {name: 0.0 for name in DEFAULT_HTML_CLASS_ORDER}

    if RE_PUBLICATION.search(low):
        class_scores["publication"] += 2.8
    if RE_REPOSITORY.search(low):
        class_scores["repository"] += 2.8
    if RE_HERITAGE.search(low):
        class_scores["heritage"] += 2.6
    if RE_BIBLIO.search(low):
        class_scores["bibliography"] += 2.3
    if RE_ADMIN.search(low):
        class_scores["admin_legal"] += 3.0
    if RE_TEACHING.search(low):
        class_scores["teaching"] += 2.2
    if RE_NEWS.search(low):
        class_scores["news"] += 2.4
    if RE_NAV.search(low):
        class_scores["navigation"] += 1.8

    # whole-page signals
    heading_blob = " ".join(txt for _, txt in parsed.headings)
    class_scores["publication"] += 0.45 * len(re.findall(RE_PUBLICATION, heading_blob))
    class_scores["repository"] += 0.40 * len(re.findall(RE_REPOSITORY, heading_blob))
    class_scores["heritage"] += 0.40 * len(re.findall(RE_HERITAGE, heading_blob))
    class_scores["bibliography"] += 0.35 * len(re.findall(RE_BIBLIO, heading_blob))
    class_scores["navigation"] += min(len(parsed.links) / 25.0, 2.0)

    # thematic relevance
    topical = weighted_keyword_score(text)
    cosine = cosine_like_score(seed_terms, text)
    relevance_score = round(1.3 * topical + 4.0 * cosine, 4)

    # refine by link ecosystem
    repo_links = sum(1 for link in parsed.links if infer_section_kind(link.section_heading) in {"repository", "bibliography"})
    pdfish_links = sum(1 for link in parsed.links if is_probable_pdf_url(link.url))
    if repo_links >= 3:
        class_scores["repository"] += 1.1
    if pdfish_links >= 3:
        class_scores["repository"] += 0.8
        class_scores["publication"] += 0.4

    page_type = max(class_scores.items(), key=lambda kv: kv[1])[0]
    reason_parts: list[str] = [f"type={page_type}", f"relevance={relevance_score:.2f}"]

    expand = False
    if page_type in {"publication", "repository", "heritage"} and relevance_score >= 0.6:
        expand = True
        reason_parts.append("expand_primary")
    elif page_type in {"bibliography", "navigation"} and relevance_score >= 1.0:
        expand = True
        reason_parts.append("expand_soft")
    elif page_type == "navigation" and pdfish_links >= 2 and topical > 0.5:
        expand = True
        reason_parts.append("expand_nav_pdf_dense")
    elif page_type == "repository" and (repo_links >= 2 or pdfish_links >= 1):
        expand = True
        reason_parts.append("expand_repo_signal")
    elif page_type == "teaching" and relevance_score >= 2.0 and pdfish_links >= 1:
        expand = True
        reason_parts.append("expand_teaching_exception")
    else:
        reason_parts.append("no_expand")

    if page_type in STOP_CLASSES and relevance_score < 2.4:
        expand = False
        reason_parts.append("hard_stop_class")

    return HtmlDecision(
        url=url,
        final_url=url,
        page_type=page_type,
        class_scores={k: round(v, 4) for k, v in class_scores.items()},
        relevance_score=relevance_score,
        expand=expand,
        reason=";".join(reason_parts),
        title=title,
        lang=parsed.lang,
        link_count=len(parsed.links),
    )


# -----------------------------------------------------------------------------
# Seeds
# -----------------------------------------------------------------------------

@dataclass
class SeedEntry:
    url: str
    label: str = ""
    topic: str = ""


def load_seed_file(path: Path) -> list[SeedEntry]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".lst"}:
        rows: list[SeedEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            rows.append(SeedEntry(url=normalize_url(s)))
        return rows

    if suffix == ".csv":
        rows = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = normalize_url(row.get("url", "").strip())
                if url:
                    rows.append(
                        SeedEntry(
                            url=url,
                            label=row.get("label", "").strip(),
                            topic=row.get("topic", "").strip(),
                        )
                    )
        return rows

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    rows.append(SeedEntry(url=normalize_url(item)))
                elif isinstance(item, dict):
                    url = normalize_url(str(item.get("url", "")).strip())
                    if url:
                        rows.append(
                            SeedEntry(
                                url=url,
                                label=str(item.get("label", "")).strip(),
                                topic=str(item.get("topic", "")).strip(),
                            )
                        )
        return rows

    if suffix in {".yaml", ".yml"} and yaml is not None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        rows = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    rows.append(SeedEntry(url=normalize_url(item)))
                elif isinstance(item, dict):
                    url = normalize_url(str(item.get("url", "")).strip())
                    if url:
                        rows.append(
                            SeedEntry(
                                url=url,
                                label=str(item.get("label", "")).strip(),
                                topic=str(item.get("topic", "")).strip(),
                            )
                        )
        return rows

    raise ValueError(f"Unsupported seed file format: {path}")


def load_seeds(paths: list[Path]) -> list[SeedEntry]:
    out: list[SeedEntry] = []
    seen: set[str] = set()
    for path in paths:
        for entry in load_seed_file(path):
            if entry.url and entry.url not in seen:
                seen.add(entry.url)
                out.append(entry)
    return out


# -----------------------------------------------------------------------------
# Crawl model
# -----------------------------------------------------------------------------

@dataclass
class CrawlConfig:
    out_dir: Path
    seed_files: list[Path]
    max_pages: int = 40
    max_depth: int = 2
    max_links_per_page: int = 40
    per_domain_page_limit: int = 12
    per_domain_pdf_limit: int = 60
    heartbeat_every: int = 10
    verbose: bool = True


@dataclass
class QueueItem:
    url: str
    depth: int
    source_url: str
    source_section_heading: str = ""
    source_section_kind: str = ""


# -----------------------------------------------------------------------------
# Main crawler
# -----------------------------------------------------------------------------

class LiteratureCrawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.logger = TaggedLogger(config.out_dir / "crawl_review.log", verbose=config.verbose)
        self.domain_store = build_domain_reputation_store()

        self.seed_entries = load_seeds(config.seed_files)
        self.seed_terms = self._build_seed_terms()

        self.frontier: deque[QueueItem] = deque()
        self.seen_html: set[str] = set()
        self.seen_pdfs: set[str] = set()

        self.domain_page_counts: Counter = Counter()
        self.domain_pdf_counts: Counter = Counter()

        self.html_decisions: list[dict[str, Any]] = []
        self.pdf_candidates: list[dict[str, Any]] = []

    def _build_seed_terms(self) -> set[str]:
        tokens: set[str] = set()
        for entry in self.seed_entries:
            tokens |= set(text_to_tokens(entry.url))
            tokens |= set(text_to_tokens(entry.label))
            tokens |= set(text_to_tokens(entry.topic))
        extra = {
            "fachwerk",
            "fachwerkhaus",
            "timber",
            "frame",
            "timber-frame",
            "vernacular",
            "architecture",
            "hallenhaus",
            "medieval",
            "historical",
            "bauforschung",
            "hausforschung",
            "heritage",
            "wealden",
            "cruck",
            "aisled",
        }
        tokens |= extra
        return {tok for tok in tokens if len(tok) >= 3}

    def seed_frontier(self) -> None:
        for entry in self.seed_entries:
            self.frontier.append(
                QueueItem(
                    url=entry.url,
                    depth=0,
                    source_url="SEED",
                )
            )

    def run(self) -> None:
        start = time.time()
        self.seed_frontier()

        self.logger.log(
            "RUN_START",
            seeds=len(self.seed_entries),
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth,
            per_domain_page_limit=self.config.per_domain_page_limit,
            per_domain_pdf_limit=self.config.per_domain_pdf_limit,
        )

        pages_done = 0
        while self.frontier and pages_done < self.config.max_pages:
            item = self.frontier.popleft()
            url = normalize_url(item.url)

            if url in self.seen_html:
                continue

            domain = safe_domain(url)
            if self.domain_page_counts[domain] >= self.config.per_domain_page_limit:
                continue

            self.seen_html.add(url)
            self.domain_page_counts[domain] += 1
            self.domain_store.note_html(domain)

            self.logger.log("FETCH_HTML", url=url, depth=item.depth, source=item.source_url)
            fetched = fetch_html(url)
            if not fetched.ok:
                self.html_decisions.append(
                    {
                        "url": url,
                        "final_url": fetched.final_url,
                        "page_type": "fetch_error",
                        "class_scores": "{}",
                        "relevance_score": 0.0,
                        "expand": False,
                        "reason": fetched.error,
                        "title": "",
                        "lang": "",
                        "link_count": 0,
                        "depth": item.depth,
                        "domain": domain,
                    }
                )
                self.logger.log("HTML_HARD_STOP", url=url, reason=fetched.error)
                continue

            parser = SectionAwareHTMLParser(fetched.final_url)
            try:
                parser.feed(fetched.html_text)
                parsed = parser.parsed()
            except Exception as exc:
                self.html_decisions.append(
                    {
                        "url": url,
                        "final_url": fetched.final_url,
                        "page_type": "parse_error",
                        "class_scores": "{}",
                        "relevance_score": 0.0,
                        "expand": False,
                        "reason": f"parse_exception:{type(exc).__name__}:{exc}",
                        "title": "",
                        "lang": "",
                        "link_count": 0,
                        "depth": item.depth,
                        "domain": domain,
                    }
                )
                self.logger.log("PARSE_HTML", url=url, ok=False, error=str(exc))
                self.logger.log("HTML_HARD_STOP", url=url, reason="parse_error")
                continue

            self.logger.log("PARSE_HTML", url=url, ok=True, title=parsed.title[:120], links=len(parsed.links))

            decision = classify_html_page(fetched.final_url, parsed, self.seed_terms)
            decision.final_url = fetched.final_url

            self.html_decisions.append(
                {
                    "url": decision.url,
                    "final_url": decision.final_url,
                    "page_type": decision.page_type,
                    "class_scores": json.dumps(decision.class_scores, sort_keys=True),
                    "relevance_score": decision.relevance_score,
                    "expand": decision.expand,
                    "reason": decision.reason,
                    "title": decision.title,
                    "lang": decision.lang,
                    "link_count": decision.link_count,
                    "depth": item.depth,
                    "domain": domain,
                }
            )

            self.logger.log(
                "HTML_DECISION",
                url=fetched.final_url,
                page_type=decision.page_type,
                relevance=f"{decision.relevance_score:.3f}",
                expand=decision.expand,
                reason=decision.reason,
                links=len(parsed.links),
            )

            if not decision.expand:
                if decision.page_type in STOP_CLASSES:
                    self.logger.log("HTML_HARD_STOP", url=fetched.final_url, reason=decision.reason)
                else:
                    self.logger.log("HTML_NO_EXPAND", url=fetched.final_url, reason=decision.reason)

            self._process_links(
                page_url=fetched.final_url,
                page_text=parsed.text,
                links=parsed.links,
                depth=item.depth,
                expand=decision.expand,
            )

            pages_done += 1
            if pages_done % self.config.heartbeat_every == 0:
                self.logger.log(
                    "HEARTBEAT",
                    pages_done=pages_done,
                    frontier=len(self.frontier),
                    pdf_candidates=len(self.pdf_candidates),
                    domains=len(self.domain_page_counts),
                )

        self._write_outputs()
        self.logger.log(
            "RUN_DONE",
            pages_done=len(self.html_decisions),
            pdf_candidates=len(self.pdf_candidates),
            domains=len(self.domain_page_counts),
            seconds=round(time.time() - start, 2),
        )
        self.logger.close()

    def _process_links(
        self,
        *,
        page_url: str,
        page_text: str,
        links: list[ParsedLink],
        depth: int,
        expand: bool,
    ) -> None:
        ranked = self._rank_links(page_text=page_text, links=links)
        html_count = 0
        pdf_count = 0
        queue_count = 0

        for link, link_score in ranked[: self.config.max_links_per_page]:
            if not link.url or link.url.startswith(("mailto:", "javascript:", "tel:")):
                continue

            domain = safe_domain(link.url)

            if is_probable_pdf_url(link.url):
                pdf_count += 1
                self._handle_pdf_candidate(
                    page_url=page_url,
                    page_text=page_text,
                    link=link,
                    link_score=link_score,
                )
                continue

            if not expand:
                continue
            if depth + 1 > self.config.max_depth:
                continue

            if link.url not in self.seen_html:
                self.frontier.append(
                    QueueItem(
                        url=link.url,
                        depth=depth + 1,
                        source_url=page_url,
                        source_section_heading=link.section_heading,
                        source_section_kind=link.section_kind,
                    )
                )
                html_count += 1
                queue_count += 1

        self.logger.log(
            "LINK_DISCOVERY_SUMMARY",
            page=page_url,
            queued_html=queue_count,
            pdf_candidates=pdf_count,
            ranked_total=len(ranked),
        )

    def _rank_links(self, *, page_text: str, links: list[ParsedLink]) -> list[tuple[ParsedLink, float]]:
        ranked: list[tuple[ParsedLink, float]] = []
        for link in links:
            score = 0.0
            combined = " ".join(
                [
                    link.anchor_text,
                    link.title,
                    link.section_heading,
                    link.surrounding_text,
                    link.url,
                ]
            )

            score += 2.0 * cosine_like_score(self.seed_terms, combined)
            score += max(0.0, weighted_keyword_score(combined))
            score += 0.8 if link.section_kind in {"bibliography", "repository", "publication", "heritage"} else 0.0
            score += 0.5 if is_probable_pdf_url(link.url) else 0.0

            if RE_ADMIN.search(combined):
                score -= 1.4
            if RE_NEWS.search(combined):
                score -= 0.5
            if "/tag/" in link.url or "/category/" in link.url:
                score -= 0.4

            ranked.append((link, round(score, 4)))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def _handle_pdf_candidate(
        self,
        *,
        page_url: str,
        page_text: str,
        link: ParsedLink,
        link_score: float,
    ) -> None:
        url = normalize_url(link.url)
        if url in self.seen_pdfs:
            return

        domain = safe_domain(url)
        if self.domain_pdf_counts[domain] >= self.config.per_domain_pdf_limit:
            return

        self.seen_pdfs.add(url)
        self.domain_pdf_counts[domain] += 1
        self.domain_store.note_pdf_checked(domain)

        verify = verify_pdf_candidate(url)
        if not verify.ok:
            self.domain_store.note_verify_fail(domain)
            self.logger.log("PDF_VERIFY_FAIL", url=url, reason=verify.reason)
        parsed_path = analyze_path_semantics(url)

        score = score_candidate(
            url=url,
            anchor_text=link.anchor_text,
            surrounding_text=link.surrounding_text,
            page_text=page_text,
            section_heading=link.section_heading,
            section_kind=link.section_kind,
            verify=verify,
            seed_terms=self.seed_terms,
            domain_store=self.domain_store,
        )
        self.domain_store.note_decision(domain, score.decision)

        row = {
            "source_page": page_url,
            "url": url,
            "final_url": verify.final_url,
            "domain": domain,
            "anchor_text": link.anchor_text,
            "surrounding_text": link.surrounding_text,
            "section_heading": link.section_heading,
            "section_kind": link.section_kind,
            "score": score.score,
            "cosine_score": score.cosine_score,
            "context_score": score.context_score,
            "url_score": score.url_score,
            "filename_score": score.filename_score,
            "path_score": score.path_score,
            "domain_score": score.domain_score,
            "repository_score": score.repository_score,
            "scientific_score": score.scientific_score,
            "semantic_score": score.semantic_score,
            "spam_risk": score.spam_risk,
            "confidence": score.confidence,
            "decision": score.decision,
            "reason": score.reason,
            "path_family": parsed_path.get("path_family", ""),
            "prototype_name": parsed_path.get("prototype_name", ""),
            "prototype_scores": parsed_path.get("prototype_scores", ""),
            "verify_ok": verify.ok,
            "verify_reason": verify.reason,
            "content_type": verify.content_type,
            "content_length": verify.content_length if verify.content_length is not None else "",
            "header_pdf": verify.header_pdf,
            "ext_pdf": verify.ext_pdf,
            "first_bytes_pdf": verify.first_bytes_pdf,
            "domain_reputation": self.domain_store.reputation(domain),
            "domain_success_rate": self.domain_store.success_rate(domain),
            "link_score": link_score,
        }
        self.pdf_candidates.append(row)

        self.logger.log(
            "PDF_CANDIDATE",
            url=url,
            decision=score.decision,
            score=f"{score.score:.3f}",
            confidence=f"{score.confidence:.3f}",
            reason=score.reason,
            section_kind=link.section_kind,
            section_heading=link.section_heading[:100],
        )

    def _write_outputs(self) -> None:
        write_csv(
            self.config.out_dir / "pdf_candidates_all.csv",
            self.pdf_candidates,
            [
                "source_page",
                "url",
                "final_url",
                "domain",
                "anchor_text",
                "surrounding_text",
                "score",
                "cosine_score",
                "context_score",
                "url_score",
                "filename_score",
                "path_score",
                "domain_score",
                "repository_score",
                "scientific_score",
                "semantic_score",
                "spam_risk",
                "confidence",
                "decision",
                "reason",
                "path_family",
                "prototype_name",
                "prototype_scores",
                "section_heading",
                "section_kind",
                "verify_ok",
                "verify_reason",
                "content_type",
                "content_length",
                "header_pdf",
                "ext_pdf",
                "first_bytes_pdf",
                "domain_reputation",
                "domain_success_rate",
                "link_score",
            ],
        )

        write_csv(
            self.config.out_dir / "html_decisions.csv",
            self.html_decisions,
            [
                "url",
                "final_url",
                "domain",
                "depth",
                "page_type",
                "class_scores",
                "relevance_score",
                "expand",
                "reason",
                "title",
                "lang",
                "link_count",
            ],
        )

        write_csv(
            self.config.out_dir / "domain_reputation_summary.csv",
            self.domain_store.summary_rows(),
            [
                "domain",
                "html_seen",
                "pdf_checked",
                "verify_fail",
                "accept",
                "maybe",
                "review",
                "reject",
                "skip",
                "reputation",
                "success_rate",
            ],
        )


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def default_seed_files(base_dir: Path) -> list[Path]:
    seed_dir = base_dir / "seeds"

    candidates = [
        seed_dir / "seed_urls_curated.txt",
        seed_dir / "seed_urls.txt",
        seed_dir / "urls.txt",
        seed_dir / "repositories.yaml",
        seed_dir / "repositories.yml",
        seed_dir / "repository_seeds.txt",
        seed_dir / "seed_domains_curated.txt",
        seed_dir / "seed_domains.txt",
        seed_dir / "domains.txt",
        seed_dir / "journals.txt",
    ]

    return [p for p in candidates if p.exists()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    pipeline_dir = script_dir.parent

    parser = argparse.ArgumentParser(description="Focused literature crawler for architecture PDFs.")
    parser.add_argument(
        "--seed-file",
        action="append",
        dest="seed_files",
        default=[],
        help="Seed file path; may be repeated. Supported: txt,csv,json,yaml,yml",
    )
    parser.add_argument(
        "--out-dir",
        default=str(pipeline_dir / "data"),
        help="Output directory for csv/log files",
    )
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-links-per-page", type=int, default=40)
    parser.add_argument("--per-domain-page-limit", type=int, default=12)
    parser.add_argument("--per-domain-pdf-limit", type=int, default=60)
    parser.add_argument("--heartbeat-every", type=int, default=10)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> CrawlConfig:
    ensure_runtime_dirs()
    script_dir = Path(__file__).resolve().parent
    pipeline_dir = script_dir.parent

    seed_files = [Path(p).resolve() for p in args.seed_files]
    if not seed_files:
        seed_files = default_seed_files(pipeline_dir)

    if not seed_files:
        raise SystemExit(
            "No seed files found. Provide --seed-file or place seed files in "
            "florilegium_project/seeds/ "
            "(e.g. seed_urls_curated.txt, seed_urls.txt, urls.txt, repositories.yaml)."
        )

    return CrawlConfig(
        out_dir=Path(args.out_dir).resolve(),
        seed_files=seed_files,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_links_per_page=args.max_links_per_page,
        per_domain_page_limit=args.per_domain_page_limit,
        per_domain_pdf_limit=args.per_domain_pdf_limit,
        heartbeat_every=args.heartbeat_every,
        verbose=not args.quiet,
    )


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        args = parse_args(argv)
        config = build_config(args)
        crawler = LiteratureCrawler(config)
        crawler.run()
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
