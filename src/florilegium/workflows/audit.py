#!/usr/bin/env python3

"""
STEP 3
PDF relevance audit

Scans downloaded PDFs and estimates topical relevance
for historical architecture / vernacular building research.

Input:
    var/data/pdf_downloads.csv

Output:
    var/data/pdf_audit.csv

Notes:
- Uses native PDF text extraction only.
- OCR is intentionally NOT used here.
- Goal is to estimate crawler precision and identify noise sources.
"""

from __future__ import annotations

from florilegium.settings import get_paths, ensure_runtime_dirs

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    import fitz  # PyMuPDF
except ModuleNotFoundError:
    fitz = None



ROOT = Path(__file__).resolve().parents[1]

DOWNLOAD_INDEX = ROOT / "data" / "pdf_downloads.csv"
OUT_AUDIT = ROOT / "data" / "pdf_audit.csv"


# --------------------------------------------------------------------
# KEYWORD SETS
# --------------------------------------------------------------------

STRONG_PHRASES = [
    "fachwerk",
    "timber frame",
    "timber-framed",
    "timber framed",
    "half timbered",
    "half-timbered",
    "vernacular architecture",
    "vernacular building",
    "building archaeology",
    "architectural history",
    "historic building",
    "historic buildings",
    "historic architecture",
    "baugeschichte",
    "bauhistor",
    "bauarchäologie",
    "bauarchaologie",
    "denkmalpflege",
    "denkmaltopographie",
    "hallenhaus",
    "hall house",
    "open hall",
    "open-hall",
    "cruck",
    "dendrochronology",
    "tree-ring",
    "tree ring",
    "medieval house",
    "medieval houses",
    "farm house",
    "farmhouse",
    "aisled barn",
    "barn frame",
    "roof structure",
    "roof truss",
    "timber construction",
    "wood construction",
    "carpentry tradition",
    "vernacular house",
    "vernacular houses",
]

MEDIUM_PHRASES = [
    "architecture",
    "architectural",
    "building",
    "buildings",
    "construction",
    "structural",
    "structure",
    "roof",
    "truss",
    "beam",
    "post",
    "wall plate",
    "frame",
    "framing",
    "timber",
    "wooden house",
    "rural house",
    "rural building",
    "village house",
    "settlement",
    "settlements",
    "dwelling",
    "dwellings",
    "house plan",
    "floor plan",
    "archaeology",
    "heritage",
    "conservation",
    "restoration",
    "monument",
    "listed building",
    "historic fabric",
    "joinery",
    "carpentry",
    "craft tradition",
    "medieval",
    "late medieval",
    "early modern",
]

WEAK_PHRASES = [
    "history",
    "historic",
    "regional",
    "traditional",
    "tradition",
    "material culture",
    "cultural heritage",
    "rural",
    "domestic architecture",
    "housing",
    "habitation",
    "settlement history",
    "wood",
    "oak",
    "spruce",
    "pine",
    "attic",
    "façade",
    "facade",
    "masonry",
    "stone",
    "brick",
]

NEGATIVE_PHRASES = [
    "tourism",
    "tourist",
    "hotel",
    "restaurant",
    "festival",
    "event",
    "events",
    "exhibition",
    "press release",
    "newsletter",
    "sports",
    "match report",
    "school inspection",
    "inspection report",
    "budget report",
    "financial statement",
    "annual report",
    "marketing",
    "travel guide",
    "visitor guide",
    "admission",
    "opening hours",
    "opening hour",
    "weather report",
    "real estate",
    "property market",
    "municipal election",
    "mayor",
    "campaign",
    "press conference",
]

VERY_NEGATIVE_PHRASES = [
    "medical",
    "biochemistry",
    "molecular",
    "clinical trial",
    "neural network",
    "particle physics",
    "financial derivatives",
    "tax regulation",
    "sports medicine",
    "veterinary",
    "epidemiology",
    "pharmacology",
]


# --------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------

def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("\x00", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def count_phrase_hits(text: str, phrases: Iterable[str]) -> tuple[int, list[str]]:
    hits: list[str] = []
    for phrase in phrases:
        if phrase in text:
            hits.append(phrase)
    return len(hits), hits


def extract_text(pdf_path: Path, max_pages: int = 5) -> str:
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""

    chunks: list[str] = []

    try:
        page_count = min(max_pages, len(doc))
        for i in range(page_count):
            try:
                page = doc[i]
                chunks.append(page.get_text())
            except Exception:
                continue
    finally:
        try:
            doc.close()
        except Exception:
            pass

    return normalize_text(" ".join(chunks))


def extract_preview(text: str, length: int = 240) -> str:
    if not text:
        return ""
    preview = text[:length].strip()
    preview = re.sub(r"\s+", " ", preview)
    return preview


def score_text(text: str) -> dict[str, object]:
    strong_n, strong_hits = count_phrase_hits(text, STRONG_PHRASES)
    medium_n, medium_hits = count_phrase_hits(text, MEDIUM_PHRASES)
    weak_n, weak_hits = count_phrase_hits(text, WEAK_PHRASES)
    neg_n, neg_hits = count_phrase_hits(text, NEGATIVE_PHRASES)
    very_neg_n, very_neg_hits = count_phrase_hits(text, VERY_NEGATIVE_PHRASES)

    # Weighted score: tuned for broader architectural relevance.
    score = (
        strong_n * 5
        + medium_n * 2
        + weak_n * 1
        - neg_n * 3
        - very_neg_n * 6
    )

    return {
        "score": score,
        "strong_n": strong_n,
        "medium_n": medium_n,
        "weak_n": weak_n,
        "neg_n": neg_n,
        "very_neg_n": very_neg_n,
        "strong_hits": strong_hits,
        "medium_hits": medium_hits,
        "weak_hits": weak_hits,
        "neg_hits": neg_hits,
        "very_neg_hits": very_neg_hits,
    }


def classify(score: int, text_length: int, strong_n: int, medium_n: int) -> str:
    # Very short text often means scan, corrupt extraction, or empty PDF.
    if text_length < 120:
        if strong_n >= 1 or medium_n >= 2:
            return "B_related"
        return "C_irrelevant"

    # Main thresholds
    if score >= 8:
        return "A_relevant"
    if score >= 3:
        return "B_related"
    return "C_irrelevant"


def load_download_index() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    with DOWNLOAD_INDEX.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "").strip() == "ok":
                rows.append(row)

    return rows


# --------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------

def run() -> None:
    if not DOWNLOAD_INDEX.exists():
        raise SystemExit(f"Download index not found: {DOWNLOAD_INDEX}")

    rows = load_download_index()
    print("PDFs to audit:", len(rows))

    class_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()

    with OUT_AUDIT.open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "pdf_url",
            "domain",
            "local_path",
            "text_length",
            "strong_hits_n",
            "medium_hits_n",
            "weak_hits_n",
            "negative_hits_n",
            "very_negative_hits_n",
            "score",
            "classification",
            "strong_hits",
            "medium_hits",
            "weak_hits",
            "negative_hits",
            "very_negative_hits",
            "text_preview",
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            local_path_raw = row.get("local_path") or ""
            path = Path(local_path_raw)

            if not path.exists():
                continue

            text = extract_text(path)
            text_length = len(text)
            preview = extract_preview(text)

            scored = score_text(text)
            classification = classify(
                score=int(scored["score"]),
                text_length=text_length,
                strong_n=int(scored["strong_n"]),
                medium_n=int(scored["medium_n"]),
            )

            record = {
                "pdf_url": row.get("pdf_url", ""),
                "domain": row.get("domain", ""),
                "local_path": local_path_raw,
                "text_length": text_length,
                "strong_hits_n": scored["strong_n"],
                "medium_hits_n": scored["medium_n"],
                "weak_hits_n": scored["weak_n"],
                "negative_hits_n": scored["neg_n"],
                "very_negative_hits_n": scored["very_neg_n"],
                "score": scored["score"],
                "classification": classification,
                "strong_hits": " | ".join(scored["strong_hits"]),
                "medium_hits": " | ".join(scored["medium_hits"]),
                "weak_hits": " | ".join(scored["weak_hits"]),
                "negative_hits": " | ".join(scored["neg_hits"]),
                "very_negative_hits": " | ".join(scored["very_neg_hits"]),
                "text_preview": preview,
            }

            writer.writerow(record)
            class_counter[classification] += 1
            domain_counter[row.get("domain", "")] += 1

    print("Audit written:", OUT_AUDIT)
    print("Classification summary:")
    for key in ("A_relevant", "B_related", "C_irrelevant"):
        print(f"  {key}: {class_counter.get(key, 0)}")


if __name__ == "__main__":
    run()


def main() -> int:
    ensure_runtime_dirs()
    paths = get_paths()
    if fitz is None:
        raise SystemExit(
            "Audit workflow requires PyMuPDF. Install dependency: pip install pymupdf"
        )
    raise SystemExit(
        "Audit workflow module imported successfully, but no CLI main() is defined yet."
    )
