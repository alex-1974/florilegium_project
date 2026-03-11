# literature_pipeline/crawler/pdf_verify.py
"""Robust PDF verifier with repository-aware fallbacks."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.request import Request, urlopen

PDF_MAGIC = b"%PDF"
TIMEOUT = 15

TRUSTED_REPO_HOSTS = {
    "archaeologydataservice.ac.uk",
    "journals.openedition.org",
    "digi.ub.uni-heidelberg.de",
    "findingaids.library.umass.edu",
    "archive.org",
    "eprints.lse.ac.uk",
    "gsarchive.net",
    "kplma.org",
}

TRUSTED_REPO_PATTERNS = (
    "/bitstream/",
    "/handle/",
    "/ead/",
    "/findingaids/",
    "/diglit/",
    "/download.pdf",
    "/download-zoom4.pdf",
    "/pdf/",
    "/archiveds/archivedownload",
    "/dissemination/pdf/",
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _looks_trusted(url: str) -> bool:
    host = _host(url)
    path = urlparse(url).path.lower()
    return host in TRUSTED_REPO_HOSTS or any(p in path for p in TRUSTED_REPO_PATTERNS)


def _fetch(url: str, *, method: str = "GET", byte_range: str | None = None):
    req = Request(
        url,
        method=method,
        headers={
            "User-Agent": "BVILLAGE-LiteraturePipeline/0.8 (+robust-pdf-verify)",
            "Accept": "application/pdf,application/octet-stream,text/html;q=0.8,*/*;q=0.5",
        },
    )
    if byte_range:
        req.add_header("Range", byte_range)
    return urlopen(req, timeout=TIMEOUT)


def verify_pdf(url: str) -> tuple[bool, str]:
    lower = url.lower()

    try:
        with _fetch(url, method="HEAD") as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            disp = (resp.headers.get("Content-Disposition") or "").lower()

            if "pdf" in ctype:
                return True, "head_content_type_pdf"
            if "octet-stream" in ctype and ("pdf" in disp or _looks_trusted(url)):
                return True, "head_octet_stream_pdfish"
    except Exception:
        pass

    try:
        with _fetch(url, method="GET", byte_range="bytes=0-1023") as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            disp = (resp.headers.get("Content-Disposition") or "").lower()
            chunk = resp.read(1024)

            if chunk.startswith(PDF_MAGIC):
                return True, "pdf_magic"
            if "pdf" in ctype:
                return True, "get_content_type_pdf"
            if "octet-stream" in ctype and ("pdf" in disp or _looks_trusted(url)):
                return True, "get_octet_stream_pdfish"
    except Exception:
        pass

    if lower.endswith(".pdf"):
        return True, "url_extension_pdf"
    if _looks_trusted(url):
        return True, "trusted_repo_pattern"

    fallbacks = []
    host = _host(url)

    if host == "journals.openedition.org" and "/pdf/" in lower:
        fallbacks.append(url + "?download=1")
    if host == "digi.ub.uni-heidelberg.de" and not lower.endswith(".pdf"):
        fallbacks.append(url.rstrip("/") + "/download.pdf")

    for candidate in fallbacks:
        try:
            with _fetch(candidate, method="GET", byte_range="bytes=0-1023") as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                chunk = resp.read(1024)
                if chunk.startswith(PDF_MAGIC) or "pdf" in ctype:
                    return True, "fallback_pdf"
        except Exception:
            continue

    return False, "not_pdf"
