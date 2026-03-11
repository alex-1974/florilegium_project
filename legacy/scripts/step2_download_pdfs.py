#!/usr/bin/env python3

"""
STEP 2
Download verified PDFs

Input:
    data/pdf_links.csv

Output:
    downloads/
    data/pdf_downloads.csv
    data/pdf_downloads.jsonl
"""

import csv
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "data"
DOWNLOADS = ROOT / "downloads"
BY_DOMAIN = DOWNLOADS / "by_domain"
LOGS = ROOT / "logs"
CACHE = ROOT / "cache"

PDF_LINKS = DATA / "pdf_links.csv"
OUT_CSV = DATA / "pdf_downloads.csv"
OUT_JSONL = DATA / "pdf_downloads.jsonl"
HASH_CACHE = CACHE / "downloaded_hashes.txt"
LOG_FILE = LOGS / "step2_download_pdfs.log"

DOWNLOADS.mkdir(exist_ok=True)
BY_DOMAIN.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

TIMEOUT = 30
PAUSE = 0.5
USER_AGENT = "LiteraturePipelineBot/0.4"


session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")
    print(msg)


def load_hash_cache():

    if not HASH_CACHE.exists():
        return set()

    with open(HASH_CACHE) as f:
        return {x.strip() for x in f}


def append_hash(h):

    with open(HASH_CACHE, "a") as f:
        f.write(h + "\n")


def sha256_bytes(data):

    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def normalize_domain(url):

    p = urlparse(url)
    return p.netloc.lower()


def filename_from_hash(h):

    return h + ".pdf"


def download_pdf(url):

    try:

        r = session.get(url, timeout=TIMEOUT)

        if r.status_code != 200:
            return None, r.status_code

        data = r.content

        if not data.startswith(b"%PDF"):
            return None, "not_pdf"

        return data, 200

    except Exception as e:

        return None, str(e)


def save_pdf(domain, data, sha):

    domain_dir = BY_DOMAIN / domain
    domain_dir.mkdir(exist_ok=True)

    name = filename_from_hash(sha)

    path = domain_dir / name

    with open(path, "wb") as f:
        f.write(data)

    return str(path)


def run():

    if not PDF_LINKS.exists():
        log("pdf_links.csv not found")
        return

    hash_cache = load_hash_cache()

    rows = []

    with open(PDF_LINKS) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    log(f"PDF candidates: {len(rows)}")

    downloaded = 0
    duplicates = 0
    errors = 0

    with open(OUT_CSV, "w", newline="") as csvfile, open(
        OUT_JSONL, "w"
    ) as jsonfile:

        fieldnames = [
            "pdf_url",
            "domain",
            "downloaded_at",
            "sha256",
            "local_path",
            "status",
        ]

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:

            url = row["pdf_url"]
            domain = normalize_domain(url)

            log(f"DOWNLOAD {url}")

            data, status = download_pdf(url)

            if data is None:

                errors += 1

                writer.writerow(
                    {
                        "pdf_url": url,
                        "domain": domain,
                        "downloaded_at": "",
                        "sha256": "",
                        "local_path": "",
                        "status": status,
                    }
                )

                continue

            sha = sha256_bytes(data)

            if sha in hash_cache:

                duplicates += 1
                log("DUPLICATE")

                writer.writerow(
                    {
                        "pdf_url": url,
                        "domain": domain,
                        "downloaded_at": "",
                        "sha256": sha,
                        "local_path": "",
                        "status": "duplicate",
                    }
                )

                continue

            path = save_pdf(domain, data, sha)

            append_hash(sha)

            downloaded += 1

            record = {
                "pdf_url": url,
                "domain": domain,
                "downloaded_at": time.time(),
                "sha256": sha,
                "local_path": path,
                "status": "ok",
            }

            writer.writerow(record)
            jsonfile.write(json.dumps(record) + "\n")

            log(f"SAVED {path}")

            time.sleep(PAUSE)

    log("")
    log("Download finished")
    log(f"downloaded: {downloaded}")
    log(f"duplicates: {duplicates}")
    log(f"errors: {errors}")


if __name__ == "__main__":
    run()
