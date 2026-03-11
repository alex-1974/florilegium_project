from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DROP_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

BINARY_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
    ".tif", ".tiff", ".ico", ".mp4", ".webm", ".mov", ".avi",
    ".mp3", ".wav", ".zip", ".rar", ".7z", ".tar", ".gz",
)

HARD_REJECT_TERMS = (
    "impressum", "datenschutz", "privacy", "kontakt", "contact",
    "jobs", "stellenangebote", "karriere", "career", "veranstaltungen",
    "events", "filme", "film", "video", "videos", "presse", "press",
    "newsletter", "leichte-sprache", "leichte_sprache", "gebaerdensprache",
    "gebardensprache", "barrierefreiheit", "accessibility", "suche",
    "search", "shop", "cart", "checkout", "login", "register", "signup",
)

def normalize_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        return raw

    parts = urlsplit(raw)

    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"

    while "//" in path:
        path = path.replace("//", "/")

    if path != "/" and path.endswith("/"):
        path = path[:-1]

    filtered_query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in DROP_QUERY_KEYS
    ]
    query = urlencode(filtered_query, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def is_probably_binary_asset(url: str) -> bool:
    u = normalize_url(url).lower()
    return any(u.endswith(ext) for ext in BINARY_EXTENSIONS)


def should_hard_reject_url(url: str) -> bool:
    u = normalize_url(url).lower()

    if is_probably_binary_asset(u):
        return True

    return any(term in u for term in HARD_REJECT_TERMS)
