#!/usr/bin/env python3

import csv
import hashlib
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import yaml
from bs4 import BeautifulSoup

USER_AGENT = "BVILLAGE-literature-bot/0.1"
TIMEOUT = 20
RETRIES = 3


# -------------------------------------------------------
# helpers
# -------------------------------------------------------

def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def progress(current, total, label=""):
    width = 28
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    print(f"\r[{bar}] {current}/{total} {label}", end="", flush=True)
    if current == total:
        print()


# -------------------------------------------------------
# filesystem
# -------------------------------------------------------

def ensure_dirs(root):
    for p in [
        root/"cache/search",
        root/"cache/http",
        root/"data",
        root/"logs"
    ]:
        p.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------------
# seed loading
# -------------------------------------------------------

def load_seed_links(root, path):

    seed_path = root / path

    if not seed_path.exists():
        print(f"Seed CSV not found: {seed_path}")
        return []

    urls = []

    with open(seed_path) as f:
        r = csv.DictReader(f)
        for row in r:
            url = row.get("url") or row.get("link")
            if url:
                urls.append(url.strip())

    print(f"Loaded seeds: {len(urls)}")
    return urls


# -------------------------------------------------------
# search
# -------------------------------------------------------

def search_query(session, root, query):

    cache_file = root/"cache/search"/f"{sha256(query)}.html"

    if cache_file.exists():
        return cache_file.read_text()

    url = "https://duckduckgo.com/html/"

    for i in range(RETRIES):

        try:
            r = session.post(
                url,
                data={"q":query},
                headers={"User-Agent":USER_AGENT},
                timeout=TIMEOUT
            )

            r.raise_for_status()

            cache_file.write_text(r.text)
            return r.text

        except Exception:
            time.sleep(2**i)

    raise RuntimeError("search failed")


def extract_links(html):

    soup = BeautifulSoup(html,"html.parser")
    urls = []

    for a in soup.select("a[href]"):

        href = a.get("href")

        if ".pdf" in href.lower():
            urls.append(href)

    return urls


# -------------------------------------------------------
# verify pdf
# -------------------------------------------------------

def verify_pdf(session, root, url):

    key = sha256(url)
    cache_file = root/"cache/http"/f"{key}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    record = {
        "url":url,
        "verified":False,
        "content_type":None
    }

    try:

        r = session.head(
            url,
            allow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent":USER_AGENT}
        )

        ct = r.headers.get("content-type","")

        if "pdf" in ct.lower():
            record["verified"] = True

        record["content_type"] = ct

    except:
        pass

    cache_file.write_text(json.dumps(record))
    return record


# -------------------------------------------------------
# main
# -------------------------------------------------------

def main():

    root = Path(__file__).resolve().parent.parent

    print(f"\nPipeline root: {root}\n")

    ensure_dirs(root)

    config = yaml.safe_load(open(root/"config/queries.yaml"))

    queries = config["queries"]
    seed_csv = config.get("seed_csv")

    session = requests.Session()

    seed_links = load_seed_links(root, seed_csv) if seed_csv else []

    # -------------------------------------------
    # search
    # -------------------------------------------

    print("\nSEARCH\n")

    candidates = set(seed_links)

    for i,q in enumerate(queries,1):

        progress(i,len(queries),q[:30])

        html = search_query(session,root,q)

        links = extract_links(html)

        candidates.update(links)

    candidates = list(candidates)

    # -------------------------------------------
    # verify
    # -------------------------------------------

    print("\nVERIFY\n")

    verified = []

    for i,url in enumerate(candidates,1):

        progress(i,len(candidates))

        v = verify_pdf(session,root,url)

        if v["verified"]:
            verified.append(url)

    # -------------------------------------------
    # write csv
    # -------------------------------------------

    raw_csv = root/"data/links_raw.csv"
    ver_csv = root/"data/links_verified.csv"

    with open(raw_csv,"w") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in candidates:
            w.writerow([u])

    with open(ver_csv,"w") as f:
        w = csv.writer(f)
        w.writerow(["url"])
        for u in verified:
            w.writerow([u])

    summary = {

        "generated_at":datetime.utcnow().isoformat(),
        "queries":len(queries),
        "candidate_links":len(candidates),
        "verified_links":len(verified),
        "raw_csv":str(raw_csv),
        "verified_csv":str(ver_csv)

    }

    (root/"logs"/"step1_summary.json").write_text(json.dumps(summary,indent=2))

    print("\nVerified PDFs:",len(verified))


if __name__ == "__main__":
    main()
