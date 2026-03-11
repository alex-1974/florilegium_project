"""Hybrid scoring for PDF candidates."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable
from urllib.parse import urlparse, unquote
import math
import re

from .path_semantics import analyze_path

__all__ = [
    "CandidateContext",
    "ScoreBreakdown",
    "score_candidate",
    "normalize_path_family",
    "slugify_reason",
]

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9._+/-]*", re.IGNORECASE)


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    text = unquote(value)
    text = text.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return phrase in haystack


def slugify_reason(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _norm_text(text)).strip("_")


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _depth_penalty(depth: int) -> float:
    if depth <= 1:
        return 0.0
    return min(0.15, 0.03 * (depth - 1))


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def normalize_path_family(url: str) -> str:
    parsed = urlparse(url)
    path = _norm_text(parsed.path)
    if not path:
        return "root"
    parts = [part for part in path.split("/") if part]
    return "/".join(parts[:2]) if parts else "root"


@dataclass(frozen=True, slots=True)
class CandidateContext:
    pdf_url: str
    source_page: str
    domain: str
    anchor_text: str = ""
    page_title: str = ""
    h1_text: str = ""
    nearby_text: str = ""
    surrounding_text: str = ""
    section_heading: str = ""
    section_kind: str = ""
    depth: int = 0
    verified_is_pdf: bool = True
    semantic_score: float = 0.0
    domain_reputation: float = 0.0
    domain_success_rate: float = 0.0

    @property
    def url_text(self) -> str:
        parsed = urlparse(self.pdf_url)
        parts = [parsed.netloc, parsed.path, parsed.query]
        return _norm_text(" ".join(part for part in parts if part))

    @property
    def source_text(self) -> str:
        return _norm_text(
            " ".join(
                x
                for x in (
                    self.anchor_text,
                    self.page_title,
                    self.h1_text,
                    self.nearby_text,
                    self.surrounding_text,
                    self.section_heading,
                )
                if x
            )
        )

    @property
    def filename_text(self) -> str:
        return _norm_text(urlparse(self.pdf_url).path.split("/")[-1])


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    total_score: float
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
    confidence: str
    decision: str
    primary_reason: str
    matched_positive: tuple[str, ...]
    matched_negative: tuple[str, ...]
    matched_scientific: tuple[str, ...]
    path_family: str
    prototype_name: str
    prototype_scores: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_POLICY: dict[str, object] = {
    "thresholds": {
        "accept": 0.68,
        "review": 0.40,
        "gate": 0.08,
        "hard_reject_negative_matches": 4,
    },
    "weights": {
        "cosine_score": 0.34,
        "semantic_score": 0.14,
        "context_score": 0.12,
        "url_score": 0.05,
        "filename_score": 0.11,
        "scientific_score": 0.07,
        "repository_score": 0.11,
        "domain_score": 0.08,
        "path_score": 0.10,
        "spam_risk": 0.12,
    },
    "positive_phrases": [
        "vernacular architecture", "vernacular building", "timber frame", "timber framed",
        "fachwerk", "building archaeology", "architectural history", "construction history",
        "historic buildings", "historic building", "historic house", "medieval house",
        "hall house", "wealden", "cruck", "aisled", "joinery", "carpentry",
        "dendrochronology", "bauforschung", "hausforschung", "monument", "heritage",
        "inventory", "catalogue", "denkmaltopographie", "farmhouse", "barn", "house",
    ],
    "negative_phrases": [
        "admission", "application form", "registration form", "privacy notice", "privacy policy",
        "gdpr", "dsgvo", "datenschutz", "consent form", "waiver", "newsletter", "brochure",
        "flyer", "course", "teaching", "lecture", "slides", "worksheet", "syllabus",
        "module handbook", "moodle", "campus", "exam", "press release", "tourism",
        "visitor guide", "invoice", "receipt", "terms and conditions", "login", "register",
    ],
    "scientific_phrases": [
        "abstract", "references", "bibliography", "journal", "volume", "issue", "doi",
        "conference paper", "peer reviewed", "research article", "full text", "publication",
        "publications", "proceedings", "thesis", "dissertation", "monograph",
        "finding aid", "findingaids", "ead",
    ],
    "axis_keywords": {
        "vernacular_building": [
            "vernacular", "farmhouse", "rural house", "rural building", "domestic architecture",
            "house history", "hall house", "wealden", "open hall", "homestead", "barn",
        ],
        "timber_or_carpentry": [
            "timber", "fachwerk", "carpentry", "joinery", "cruck", "aisled", "frame",
            "framing", "wood", "oak", "charpente",
        ],
        "medieval_or_historic": [
            "medieval", "historic", "historical", "early modern", "dendrochronology", "chronology",
        ],
        "architecture_or_building_history": [
            "architecture", "architectural history", "building archaeology", "construction history",
            "building history", "hausforschung", "bauforschung",
        ],
        "archaeology_or_heritage": [
            "heritage", "monument", "listed building", "inventory", "catalogue", "denkmal",
            "denkmalpflege", "historic environment", "dehio", "kunstdenkmal",
        ],
        "catalog_or_inventory": [
            "catalogue", "catalog", "inventory", "register", "listing", "jahrgang",
            "jahresbericht", "finding aid", "findingaids", "ead",
        ],
        "repository_form": [
            "repository", "download", "bitstream", "handle", "record", "full text",
            "pdf", "archive", "open access", "dissemination",
        ],
        "admin_noise": [
            "privacy", "gdpr", "dsgvo", "application", "registration", "consent form",
            "waiver", "newsletter", "invoice", "contact",
        ],
        "teaching_noise": [
            "course", "teaching", "lecture", "slides", "syllabus", "worksheet", "campus",
            "module handbook",
        ],
        "news_or_popular": [
            "press release", "newsletter", "visitor guide", "tourism", "magazine",
            "blog", "news", "brochure", "flyer",
        ],
    },
    "pdf_prototypes": {
        "scholarly_relevant_pdf": (0.95, 0.90, 0.80, 0.95, 0.65, 0.30, 0.35, 0.00, 0.00, 0.00),
        "heritage_catalog_pdf":   (0.55, 0.35, 0.70, 0.55, 0.95, 0.95, 0.35, 0.00, 0.00, 0.00),
        "technical_construction_pdf": (0.45, 0.98, 0.60, 0.80, 0.35, 0.10, 0.25, 0.00, 0.00, 0.00),
        "generic_repository_pdf": (0.15, 0.15, 0.20, 0.15, 0.10, 0.15, 1.00, 0.00, 0.00, 0.00),
        "administrative_pdf":     (0.00, 0.00, 0.05, 0.00, 0.00, 0.00, 0.10, 1.00, 0.20, 0.10),
        "teaching_pdf":           (0.10, 0.15, 0.10, 0.20, 0.00, 0.00, 0.10, 0.15, 1.00, 0.10),
        "noise_pdf":              (0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.05, 0.20, 0.20, 1.00),
    },
}


def _policy_list(policy: dict[str, object], key: str) -> tuple[str, ...]:
    value = policy.get(key, ())
    if isinstance(value, list):
        return tuple(str(x).lower() for x in value)
    return ()


def filename_score(url: str) -> float:
    name = urlparse(url).path.split("/")[-1].lower()
    tokens = re.split(r"[_.\- ]+", name)
    keywords = {
        "architecture", "vernacular", "timber", "fachwerk", "building", "construction",
        "medieval", "house", "dendro", "joinery", "carpentry", "historic", "archaeology",
        "bauforschung", "hausforschung", "cruck", "wealden", "hall", "barn", "dehio",
    }
    score = 0.0
    for token in tokens:
        if token in keywords:
            score += 0.12
    return min(score, 0.50)


def repository_score_from_url(url: str, domain: str) -> float:
    repo_patterns = [
        "archive.org", "handle.net", "bitstream", "eprints", "dspace", "openaire",
        "zenodo", "jstor", "archaeologydataservice", "perspectivia", "heidelberg",
        "hal.archives", "core.ac.uk", "ojs", "openaccess", "openedition",
        "findingaids", "ead",
    ]
    haystack_url = url.lower()
    haystack_domain = domain.lower()
    score = 0.0
    for pattern in repo_patterns:
        if pattern in haystack_url or pattern in haystack_domain:
            score += 0.40
    if "/bitstream/" in haystack_url:
        score += 0.20
    if "/handle/" in haystack_url:
        score += 0.20
    if "/ead/" in haystack_url or "findingaids" in haystack_url:
        score += 0.15
    return min(score, 0.90)


def _pdf_axis_vector(ctx: CandidateContext, policy: dict[str, object]) -> tuple[float, ...]:
    axis_keywords_raw = policy.get("axis_keywords", {})
    text = _norm_text(
        " ".join(
            [
                ctx.anchor_text,
                ctx.page_title,
                ctx.h1_text,
                ctx.nearby_text,
                ctx.surrounding_text,
                ctx.url_text,
                ctx.filename_text,
                ctx.section_heading,
            ]
        )
    )
    axis_order = (
        "vernacular_building",
        "timber_or_carpentry",
        "medieval_or_historic",
        "architecture_or_building_history",
        "archaeology_or_heritage",
        "catalog_or_inventory",
        "repository_form",
        "admin_noise",
        "teaching_noise",
        "news_or_popular",
    )

    axes = []
    for axis_name in axis_order:
        kws = [str(x).lower() for x in axis_keywords_raw.get(axis_name, [])]
        hit_count = sum(1 for kw in kws if kw in text)
        denom = max(2.0, min(6.0, float(len(kws)) * 0.6)) if kws else 2.0
        axes.append(_clip01(hit_count / denom))
    return tuple(axes)


def _prototype_match(pdf_vector: tuple[float, ...], policy: dict[str, object]) -> tuple[str, float, dict[str, float]]:
    raw = policy.get("pdf_prototypes", {})
    scores = {}
    for name, vec in raw.items():
        proto = tuple(float(x) for x in vec)
        scores[str(name)] = _clip01(_cosine(pdf_vector, proto))
    if not scores:
        return "none", 0.0, {}
    best_name = max(scores, key=scores.get)
    return best_name, scores[best_name], scores


def score_candidate(ctx: CandidateContext, policy: dict[str, object] | None = None) -> ScoreBreakdown:
    merged = dict(DEFAULT_POLICY)
    if policy:
        merged.update(policy)

    thresholds = dict(DEFAULT_POLICY["thresholds"])
    thresholds.update(merged.get("thresholds", {}))
    weights = dict(DEFAULT_POLICY["weights"])
    weights.update(merged.get("weights", {}))

    source_text = ctx.source_text
    url_text = ctx.url_text
    path_family = normalize_path_family(ctx.pdf_url)

    positive_phrases = _policy_list(merged, "positive_phrases")
    negative_phrases = _policy_list(merged, "negative_phrases")
    scientific_phrases = _policy_list(merged, "scientific_phrases")

    pos_ctx = tuple(p for p in positive_phrases if _contains_phrase(source_text, p))
    neg_ctx = tuple(p for p in negative_phrases if _contains_phrase(source_text, p))
    sci_ctx = tuple(p for p in scientific_phrases if _contains_phrase(source_text, p))
    pos_url = tuple(p for p in positive_phrases if _contains_phrase(url_text, p))
    neg_url = tuple(p for p in negative_phrases if _contains_phrase(url_text, p))

    section_bonus = 0.0
    if ctx.section_kind == "literature":
        section_bonus += 0.18
    elif ctx.section_kind == "publication":
        section_bonus += 0.14
    elif ctx.section_kind == "downloads":
        section_bonus += 0.12
    elif ctx.section_kind == "negative":
        section_bonus -= 0.20

    context_val = _clip01(0.16 * len(pos_ctx) - 0.20 * len(neg_ctx) + 0.08 * len(sci_ctx) + section_bonus)
    url_val = _clip01(0.16 * len(pos_url) - 0.20 * len(neg_url))
    filename_val = filename_score(ctx.pdf_url)
    path_info = analyze_path(ctx.pdf_url)
    path_val = _clip01(0.55 * path_info.pattern_score + 0.45 * path_info.prototype_score)
    scientific_val = _clip01(0.12 * len(sci_ctx))
    repo_val = _clip01(repository_score_from_url(ctx.pdf_url, ctx.domain))
    domain_val = _clip01(max(0.0, ctx.domain_reputation) + 0.35 * max(0.0, ctx.domain_success_rate))
    semantic_val = _clip01(ctx.semantic_score)

    spam_val = 0.0
    spam_val += 0.18 * len(neg_ctx)
    spam_val += 0.14 * len(neg_url)
    spam_val += _depth_penalty(ctx.depth)
    if ctx.section_kind == "negative":
        spam_val += 0.10
    spam_val += 0.08 * path_info.adminness
    spam_val += 0.06 * path_info.teachingness
    spam_val += 0.06 * path_info.newsness
    spam_val = _clip01(spam_val)

    pdf_vector = _pdf_axis_vector(ctx, merged)
    prototype_name, cosine_val, prototype_scores = _prototype_match(pdf_vector, merged)

    gated_input = (
        0.32 * cosine_val
        + 0.20 * repo_val
        + 0.14 * path_val
        + 0.12 * filename_val
        + 0.10 * context_val
        + 0.07 * semantic_val
        + 0.05 * domain_val
    )

    total = (
        weights["cosine_score"] * cosine_val
        + weights["semantic_score"] * semantic_val
        + weights["context_score"] * context_val
        + weights["url_score"] * url_val
        + weights["filename_score"] * filename_val
        + weights["scientific_score"] * scientific_val
        + weights["repository_score"] * repo_val
        + weights["domain_score"] * domain_val
        + weights["path_score"] * path_val
        - weights["spam_risk"] * spam_val
    )
    total = _clip01(total)

    negative_hit_count = len(set(neg_ctx) | set(neg_url))

    if not ctx.verified_is_pdf:
        decision, confidence, reason = "reject", "hard", "reject:not_pdf"
    elif negative_hit_count >= int(thresholds["hard_reject_negative_matches"]):
        decision, confidence, reason = "reject", "hard", "reject:administrative_or_teaching_pdf"
    elif gated_input < float(thresholds["gate"]):
        decision, confidence, reason = "reject", "low", "reject:weak_pre_gate"
    elif total >= float(thresholds["accept"]):
        decision, confidence, reason = "accept", "high", "accept:strong_candidate"
    elif total >= float(thresholds["review"]):
        decision, confidence, reason = "review", "medium", "review:needs_human_check"
    else:
        decision, confidence, reason = "reject", "low", "reject:low_final_score"

    prototype_scores_text = ";".join(f"{k}:{v:.4f}" for k, v in sorted(prototype_scores.items()))

    return ScoreBreakdown(
        total_score=round(total, 6),
        cosine_score=round(cosine_val, 6),
        context_score=round(context_val, 6),
        url_score=round(url_val, 6),
        filename_score=round(filename_val, 6),
        path_score=round(path_val, 6),
        domain_score=round(domain_val, 6),
        repository_score=round(repo_val, 6),
        scientific_score=round(scientific_val, 6),
        semantic_score=round(semantic_val, 6),
        spam_risk=round(spam_val, 6),
        confidence=confidence,
        decision=decision,
        primary_reason=f"{reason}|pathpat:{path_info.pattern_name}|pathproto:{path_info.prototype_name}",
        matched_positive=tuple(sorted(set(pos_ctx) | set(pos_url))),
        matched_negative=tuple(sorted(set(neg_ctx) | set(neg_url))),
        matched_scientific=tuple(sorted(set(sci_ctx))),
        path_family=path_family,
        prototype_name=prototype_name,
        prototype_scores=prototype_scores_text,
    )
