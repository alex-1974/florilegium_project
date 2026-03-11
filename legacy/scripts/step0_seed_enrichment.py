#!/usr/bin/env python3

from __future__ import annotations

import requests
import yaml
import pathlib
import time
import re
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT / "config"
SEED_DIR = ROOT / "seeds"

SEED_DIR.mkdir(exist_ok=True)

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

HEADERS = {
    "User-Agent": "LiteraturePipelineBot/0.4 (academic research crawler)"
}

# ------------------------------
# helpers
# ------------------------------

def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

# ------------------------------
# load topics
# ------------------------------

def load_topics():
    queries_file = CONFIG_DIR / "queries.yaml"

    if not queries_file.exists():
        print("queries.yaml not found:", queries_file)
        return []

    with open(queries_file, "r", encoding="utf-8") as f:
        q = yaml.safe_load(f) or {}

    topics = []

    if isinstance(q.get("terms"), list):
        for entry in q["terms"]:
            if isinstance(entry, str) and entry.strip():
                topics.append(entry.strip())

    topics = sorted(set(topics))
    print("Loaded topics:", topics)
    return topics


# ------------------------------
# wikipedia search
# ------------------------------

def wikipedia_search(topic):

    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srsearch": topic,
        "srlimit": 10
    }

    r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=20)

    data = r.json()

    pages = []

    for hit in data["query"]["search"]:
        pages.append(hit["title"])

    return pages


# ------------------------------
# wikipedia external links
# ------------------------------

def wikipedia_links(title):

    params = {
        "action": "query",
        "prop": "extlinks",
        "titles": title,
        "ellimit": 50,
        "format": "json"
    }

    r = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=20)

    data = r.json()

    urls = []

    pages = data["query"]["pages"]

    for p in pages.values():
        if "extlinks" not in p:
            continue

        for link in p["extlinks"]:
            urls.append(link["*"])

    return urls


# ------------------------------
# wikidata query
# ------------------------------

def wikidata_websites(label):

    query = f"""
    SELECT ?website WHERE {{
      ?item rdfs:label "{label}"@en .
      ?item wdt:P856 ?website .
    }}
    """

    r = requests.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers=HEADERS,
        timeout=30
    )

    data = r.json()

    urls = []

    for b in data["results"]["bindings"]:
        urls.append(b["website"]["value"])

    return urls


# ------------------------------
# main
# ------------------------------

def run():

    topics = load_topics()
    print("Loaded topics:", len(topics))

    all_urls = set()
    all_domains = set()

    for topic in topics:

        print("TOPIC:", topic)
        pages = wikipedia_search(topic)
        print("Wikipedia pages:", len(pages), pages[:5])

        try:

            pages = wikipedia_search(topic)

            for p in pages:

                links = wikipedia_links(p)

                for url in links:

                    all_urls.add(url)

                    d = domain_from_url(url)
                    if d:
                        all_domains.add(d)

                time.sleep(0.5)

            wikidata_urls = wikidata_websites(topic)

            for url in wikidata_urls:

                all_urls.add(url)

                d = domain_from_url(url)
                if d:
                    all_domains.add(d)

        except Exception as e:

            print("ERROR", topic, e)

    # write seeds

    with open(SEED_DIR / "seed_urls.txt", "w") as f:

        for u in sorted(all_urls):
            f.write(u + "\n")

    with open(SEED_DIR / "seed_domains.txt", "w") as f:

        for d in sorted(all_domains):
            f.write(d + "\n")

    with open(SEED_DIR / "topic_terms.txt", "w") as f:

        for t in topics:
            f.write(t + "\n")

    print("Seeds generated:")
    print("urls:", len(all_urls))
    print("domains:", len(all_domains))


if __name__ == "__main__":
    run()
