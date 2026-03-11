from __future__ import annotations

import math
import re
from collections import Counter


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str):
    return [t.lower() for t in TOKEN_RE.findall(text)]


class BM25:

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = []
        self.doc_freq = Counter()
        self.avg_len = 0

    def build(self, docs):

        self.docs = [tokenize(d) for d in docs]

        N = len(self.docs)

        total_len = 0

        for doc in self.docs:

            total_len += len(doc)

            for term in set(doc):
                self.doc_freq[term] += 1

        if N:
            self.avg_len = total_len / N
        else:
            self.avg_len = 1

    def idf(self, term):

        df = self.doc_freq.get(term, 0)

        N = len(self.docs)

        return math.log((N - df + 0.5) / (df + 0.5) + 1)

    def score(self, query_tokens, document):

        tokens = tokenize(document)

        freq = Counter(tokens)

        score = 0

        dl = len(tokens)

        for term in query_tokens:

            if term not in freq:
                continue

            tf = freq[term]

            idf = self.idf(term)

            denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avg_len)

            score += idf * tf * (self.k1 + 1) / denom

        return score
