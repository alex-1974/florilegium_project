# literature_pipeline/crawler/path_semantics.py
"""Path semantics for scholarly / repository URLs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
import math
import re

__all__ = [
    "PathSemantics",
    "analyze_path",
]


_SEGMENT_SPLIT_RE = re.compile(r"[\\/]+")
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


KNOWN_REPO_PATTERNS: dict[str, tuple[str, ...]] = {
    "dspace": ("/bitstream/", "/handle/", "/jspui/handle/", "/xmlui/handle/"),
    "eprints": ("/id/eprint/", "/eprint/", "/cgi/export/eprint/"),
    "ojs": ("/article/view/", "/article/download/", "/article/pdf/"),
    "openedition": ("/journals/", "/pdf/"),
    "ead": ("/ead/", "/findingaids/"),
    "ads": ("archaeologydataservice", "archiveDS/archiveDownload", "/dissemination/pdf/"),
    "heidelberg": ("/diglit/", "/download.pdf", "/download-zoom4.pdf"),
}

REPOSITORY_TOKENS = {
    "repository", "archive", "archives", "bitstream", "handle", "record", "ead",
    "findingaids", "diglit", "archiveDownload", "archiveDS", "collection",
    "collections", "repository", "catalog", "catalogue", "items", "object",
}
DOCUMENT_TOKENS = {
    "download", "pdf", "fulltext", "publication", "article", "report", "monograph",
    "thesis", "dissemination", "view", "document",
}
SERIAL_TOKENS = {
    "issue", "volume", "vol", "band", "jahrgang", "series", "bd", "heft",
}
TOPIC_TOKENS = {
    "vernacular", "timber", "fachwerk", "carpentry", "joinery", "cruck", "dehio",
    "barn", "house", "historic", "heritage", "architecture", "archaeology",
    "building",
}
ADMIN_TOKENS = {
    "privacy", "cookie", "login", "register", "apply", "application",
    "newsletter", "consent",
}
TEACHING_TOKENS = {
    "course", "slides", "teaching", "lecture", "seminar", "syllabus",
}
NEWS_TOKENS = {
    "news", "newsletter", "blog", "event", "events", "press", "magazine",
}

PATH_PROTOTYPES: dict[str, tuple[float, ...]] = {
    # repository, document, serial, topic, admin, teaching, news
    "trusted_repository_download": (1.00, 1.00, 0.20, 0.30, 0.00, 0.00, 0.00),
    "scholarly_document_path":    (0.55, 0.90, 0.35, 0.70, 0.00, 0.00, 0.00),
    "catalog_record_path":        (0.80, 0.35, 0.30, 0.30, 0.00, 0.00, 0.00),
    "administrative_path":        (0.00, 0.10, 0.00, 0.00, 1.00, 0.20, 0.10),
    "teaching_path":              (0.00, 0.10, 0.00, 0.10, 0.10, 1.00, 0.20),
    "noise_path":                 (0.00, 0.00, 0.00, 0.00, 0.10, 0.10, 1.00),
}


@dataclass(frozen=True, slots=True)
class PathSemantics:
    repositoryness: float
    documentness: float
    serialness: float
    topicness: float
    adminness: float
    teachingness: float
    newsness: float
    pattern_name: str
    pattern_score: float
    prototype_name: str
    prototype_score: float

    @property
    def vector(self) -> tuple[float, ...]:
        return (
            self.repositoryness,
            self.documentness,
            self.serialness,
            self.topicness,
            self.adminness,
            self.teachingness,
            self.newsness,
        )


def analyze_path(url: str) -> PathSemantics:
    parsed = urlparse(url)
    path = parsed.path.lower()
    segments = [seg for seg in _SEGMENT_SPLIT_RE.split(path) if seg]
    tokens: list[str] = []
    for seg in segments:
        tokens.extend(tok for tok in _TOKEN_SPLIT_RE.split(seg) if tok)

    repository = document = serial = topic = admin = teaching = news = 0.0

    for tok in tokens:
        if tok in REPOSITORY_TOKENS:
            repository += 0.22
        if tok in DOCUMENT_TOKENS:
            document += 0.18
        if tok in SERIAL_TOKENS:
            serial += 0.16
        if tok in TOPIC_TOKENS:
            topic += 0.14
        if tok in ADMIN_TOKENS:
            admin += 0.22
        if tok in TEACHING_TOKENS:
            teaching += 0.22
        if tok in NEWS_TOKENS:
            news += 0.22

    joined = "/".join(segments)

    if segments and segments[-1].endswith(".pdf"):
        document += 0.18
    if "download.pdf" in joined or "download-zoom4.pdf" in joined:
        document += 0.22
        repository += 0.14
    if "/pdf/" in path:
        document += 0.16

    best_pattern_name = "generic"
    best_pattern_score = 0.0
    for name, patterns in KNOWN_REPO_PATTERNS.items():
        hits = sum(1 for p in patterns if p.lower() in path or p.lower() in parsed.netloc.lower())
        if hits:
            score = min(1.0, 0.35 + 0.18 * hits)
            if score > best_pattern_score:
                best_pattern_name = name
                best_pattern_score = score

    repository = _clip01(max(repository, best_pattern_score))
    document = _clip01(document)
    serial = _clip01(serial)
    topic = _clip01(topic)
    admin = _clip01(admin)
    teaching = _clip01(teaching)
    news = _clip01(news)

    vector = (repository, document, serial, topic, admin, teaching, news)

    prototype_scores = {
        name: _clip01(_cosine(vector, proto))
        for name, proto in PATH_PROTOTYPES.items()
    }
    prototype_name = max(prototype_scores, key=prototype_scores.get)
    prototype_score = prototype_scores[prototype_name]

    return PathSemantics(
        repositoryness=repository,
        documentness=document,
        serialness=serial,
        topicness=topic,
        adminness=admin,
        teachingness=teaching,
        newsness=news,
        pattern_name=best_pattern_name,
        pattern_score=round(best_pattern_score, 6),
        prototype_name=prototype_name,
        prototype_score=round(prototype_score, 6),
    )
