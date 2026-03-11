# literature_pipeline/crawler/html_classifier.py

import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9]+")


def normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = text.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", text)


def tokens(text):
    return _WORD.findall(normalize(text))


LEGAL_TERMS = [
    "privacy",
    "gdpr",
    "dsgvo",
    "impressum",
    "legal notice",
    "cookie policy",
]

NAV_TERMS = [
    "home",
    "about",
    "contact",
    "navigation",
]

PUBLICATION_TERMS = [
    "journal",
    "article",
    "paper",
    "research",
    "publication",
    "volume",
    "issue",
]

REFERENCE_TERMS = [
    "bibliography",
    "references",
    "sources",
    "literature",
    "weiterführende literatur",
    "further reading",
]


@dataclass
class HtmlClassification:

    legal: float
    navigation: float
    publication: float
    reference: float

    page_type: str


def classify_html(title, text):

    text = normalize(title + " " + text)

    legal = sum(1 for t in LEGAL_TERMS if t in text) * 0.25
    navigation = sum(1 for t in NAV_TERMS if t in text) * 0.2
    publication = sum(1 for t in PUBLICATION_TERMS if t in text) * 0.2
    reference = sum(1 for t in REFERENCE_TERMS if t in text) * 0.3

    legal = min(1.0, legal)
    navigation = min(1.0, navigation)
    publication = min(1.0, publication)
    reference = min(1.0, reference)

    scores = {
        "legal_page": legal,
        "navigation_page": navigation,
        "publication_page": publication,
        "reference_page": reference,
    }

    page_type = max(scores, key=scores.get)

    return HtmlClassification(
        legal=legal,
        navigation=navigation,
        publication=publication,
        reference=reference,
        page_type=page_type,
    )
