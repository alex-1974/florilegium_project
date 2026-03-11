from __future__ import annotations

from .structural_bm25 import BM25, tokenize


class StructuralBM25Ranker:

    def __init__(self, topic_terms):

        self.query_tokens = tokenize(" ".join(topic_terms))

        self.bm25 = BM25()

        # minimal corpus
        self.bm25.build([" ".join(topic_terms)])

        self.weights = {
            "anchor": 4.0,
            "title": 3.0,
            "h1": 3.0,
            "url": 2.0,
            "context": 1.5,
            "page": 1.0,
        }

    def score(self, candidate):

        score = 0

        score += self.weights["anchor"] * self.bm25.score(
            self.query_tokens,
            candidate.get("anchor", "")
        )

        score += self.weights["title"] * self.bm25.score(
            self.query_tokens,
            candidate.get("title", "")
        )

        score += self.weights["h1"] * self.bm25.score(
            self.query_tokens,
            " ".join(candidate.get("h1", []))
        )

        score += self.weights["url"] * self.bm25.score(
            self.query_tokens,
            candidate.get("url", "")
        )

        score += self.weights["context"] * self.bm25.score(
            self.query_tokens,
            candidate.get("context", "")
        )

        score += self.weights["page"] * self.bm25.score(
            self.query_tokens,
            candidate.get("page_text", "")
        )

        return score
