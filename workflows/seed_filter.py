#!/usr/bin/env python3
"""
STEP 0B
Seed filtering and prioritization

Input:
    seeds/seed_urls.txt
    seeds/seed_domains.txt

Output:
    seeds/seed_urls_curated.txt
    seeds/seed_domains_curated.txt
    seeds/seed_stats.json
"""

from pathlib import Path
from urllib.parse import urlparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "seeds"

URL_FILE = SEEDS / "seed_urls.txt"
DOMAIN_FILE = SEEDS / "seed_domains.txt"

OUT_URLS = SEEDS / "seed_urls_curated.txt"
OUT_DOMAINS = SEEDS / "seed_domains_curated.txt"
STATS_FILE = SEEDS / "seed_stats.json"


BLOCK_DOMAINS = {
    "youtube.com",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "amazon.com",
    "cnn.com",
    "bbc.com",
    "nytimes.com",
    "techcrunch.com",
    "polygon.com",
    "pcgamer.com",
}

HIGH_VALUE = {
    "jstor.org",
    "archive.org",
    "persee.fr",
    "tandfonline.com",
    "cambridge.org",
    "brill.com",
    "gallica.bnf.fr",
    "digi.ub.uni-heidelberg.de",
    "historicengland.org.uk",
    "vernaculararchitecture.org",
    "heritagegateway.org.uk",
    "coflein.gov.uk",
}

PATTERNS = [
    "uni",
    "university",
    "library",
    "museum",
    "heritage",
    "archive",
    "archaeology",
    "history",
    "vernacular",
    "architecture",
]


def normalize_domain(d):
    d = d.lower()
    if d.startswith("www."):
        d = d[4:]
    return d


def extract_domain(url):
    try:
        p = urlparse(url)
        return normalize_domain(p.netloc)
    except:
        return None


def domain_score(domain):

    if domain in HIGH_VALUE:
        return 100

    score = 0

    for p in PATTERNS:
        if p in domain:
            score += 5

    return score


def load_lines(path):

    if not path.exists():
        return []

    with open(path) as f:
        return [x.strip() for x in f if x.strip()]


def main():

    urls = load_lines(URL_FILE)
    domains = load_lines(DOMAIN_FILE)

    filtered_domains = set()
    filtered_urls = []

    rejected = 0

    for d in domains:

        d = normalize_domain(d)

        if d in BLOCK_DOMAINS:
            rejected += 1
            continue

        if domain_score(d) > 0:
            filtered_domains.add(d)

    for url in urls:

        d = extract_domain(url)

        if not d:
            continue

        if d in BLOCK_DOMAINS:
            rejected += 1
            continue

        if domain_score(d) > 0 or d in filtered_domains:
            filtered_urls.append(url)

    filtered_urls = sorted(set(filtered_urls))
    filtered_domains = sorted(filtered_domains)

    OUT_URLS.write_text("\n".join(filtered_urls))
    OUT_DOMAINS.write_text("\n".join(filtered_domains))

    stats = {
        "input_urls": len(urls),
        "input_domains": len(domains),
        "filtered_urls": len(filtered_urls),
        "filtered_domains": len(filtered_domains),
        "rejected": rejected,
    }

    STATS_FILE.write_text(json.dumps(stats, indent=2))

    print("Seed filtering complete")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
