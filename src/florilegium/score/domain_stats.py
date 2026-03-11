from __future__ import annotations

from collections import defaultdict


class DomainStats:
    def __init__(self):
        self.pages = defaultdict(int)
        self.pdfs = defaultdict(int)

    def record_page(self, domain: str) -> None:
        self.pages[domain] += 1

    def record_pdf(self, domain: str) -> None:
        self.pdfs[domain] += 1

    def quality(self, domain: str) -> float:
        p = self.pages[domain]
        d = self.pdfs[domain]
        return (d + 1.0) / (p + 2.0)
