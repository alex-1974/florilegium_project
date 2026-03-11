"""Adaptive domain reputation for the focused crawler."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json

__all__ = [
    "DomainStats",
    "DomainReputationStore",
]


@dataclass
class DomainStats:
    html_seen: int = 0
    pdf_checked: int = 0
    pdf_accept: int = 0
    pdf_review: int = 0
    pdf_reject: int = 0
    verify_fail: int = 0

    @property
    def success_rate(self) -> float:
        denom = max(1, self.pdf_checked)
        return (self.pdf_accept + 0.5 * self.pdf_review) / denom

    @property
    def reputation(self) -> float:
        rep = 0.0
        rep += min(0.30, 0.04 * self.pdf_accept)
        rep += min(0.18, 0.02 * self.pdf_review)
        rep += 0.18 * self.success_rate
        rep -= min(0.20, 0.02 * self.verify_fail)
        return max(0.0, min(0.80, rep))


class DomainReputationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.stats: dict[str, DomainStats] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.stats = {domain: DomainStats(**values) for domain, values in raw.items()}
        except Exception:
            self.stats = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {domain: asdict(stats) for domain, stats in self.stats.items()}
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _get(self, domain: str) -> DomainStats:
        if domain not in self.stats:
            self.stats[domain] = DomainStats()
        return self.stats[domain]

    def note_html(self, domain: str) -> None:
        self._get(domain).html_seen += 1

    def note_pdf_checked(self, domain: str) -> None:
        self._get(domain).pdf_checked += 1

    def note_verify_fail(self, domain: str) -> None:
        self._get(domain).verify_fail += 1

    def note_decision(self, domain: str, decision: str) -> None:
        stats = self._get(domain)
        if decision == "accept":
            stats.pdf_accept += 1
        elif decision == "review":
            stats.pdf_review += 1
        else:
            stats.pdf_reject += 1

    def reputation(self, domain: str) -> float:
        return self._get(domain).reputation

    def success_rate(self, domain: str) -> float:
        return self._get(domain).success_rate

    def summary_rows(self) -> list[dict[str, object]]:
        rows = []
        for domain, stats in sorted(self.stats.items(), key=lambda kv: kv[1].reputation, reverse=True):
            rows.append(
                {
                    "domain": domain,
                    "html_seen": stats.html_seen,
                    "pdf_checked": stats.pdf_checked,
                    "pdf_accept": stats.pdf_accept,
                    "pdf_review": stats.pdf_review,
                    "pdf_reject": stats.pdf_reject,
                    "verify_fail": stats.verify_fail,
                    "success_rate": round(stats.success_rate, 4),
                    "reputation": round(stats.reputation, 4),
                }
            )
        return rows
