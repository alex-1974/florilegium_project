from __future__ import annotations

from florilegium.settings import get_paths, ensure_runtime_dirs

"""
STEP 2
Download verified PDFs

Input:
    var/data/pdf_links.csv

Output:
    var/downloads/
    var/data/pdf_downloads.csv
    var/data/pdf_downloads.jsonl
"""

import csv
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

TIMEOUT = 30
PAUSE = 0.5
USER_AGENT = "Florilegium/0.1"


session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def log(msg: str, log_file: Path) -> None:
    with log_file.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def load_hash_cache(hash_cache_path: Path) -> set[str]:
    if not hash_cache_path.exists():
        return set()

    with hash_cache_path.open(encoding="utf-8") as f:
        return {x.strip() for x in f if x.strip()}


def append_hash(hash_cache_path: Path, h: str) -> None:
    with hash_cache_path.open("a", encoding="utf-8") as f:
        f.write(h + "\n")


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def normalize_domain(url: str) -> str:
    p = urlparse(url)
    return p.netloc.lower()


def filename_from_hash(h: str) -> str:
    return h + ".pdf"


def download_pdf(url: str):
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


def save_pdf(by_domain_dir: Path, domain: str, data: bytes, sha: str) -> str:
    domain_dir = by_domain_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    name = filename_from_hash(sha)
    path = domain_dir / name

    with path.open("wb") as f:
        f.write(data)

    return str(path)


def run() -> int:
    paths = ensure_runtime_dirs()

    pdf_links = paths.data_dir / "pdf_links.csv"
    out_csv = paths.data_dir / "pdf_downloads.csv"
    out_jsonl = paths.data_dir / "pdf_downloads.jsonl"
    downloads_dir = paths.downloads_dir
    by_domain_dir = downloads_dir / "by_domain"
    hash_cache = paths.cache_dir / "downloaded_hashes.txt"
    log_file = paths.logs_dir / "step2_download_pdfs.log"

    downloads_dir.mkdir(parents=True, exist_ok=True)
    by_domain_dir.mkdir(parents=True, exist_ok=True)
    paths.cache_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_links.exists():
        log(f"pdf_links.csv not found: {pdf_links}", log_file)
        return 1

    known_hashes = load_hash_cache(hash_cache)

    with pdf_links.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    log(f"PDF candidates: {len(rows)}", log_file)

    downloaded = 0
    duplicates = 0
    errors = 0

    with out_csv.open("w", encoding="utf-8", newline="") as csvfile, out_jsonl.open(
        "w", encoding="utf-8"
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

            log(f"DOWNLOAD {url}", log_file)

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

            if sha in known_hashes:
                duplicates += 1
                log("DUPLICATE", log_file)

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

            local_path = save_pdf(by_domain_dir, domain, data, sha)
            append_hash(hash_cache, sha)
            known_hashes.add(sha)

            downloaded += 1

            record = {
                "pdf_url": url,
                "domain": domain,
                "downloaded_at": time.time(),
                "sha256": sha,
                "local_path": local_path,
                "status": "ok",
            }

            writer.writerow(record)
            jsonfile.write(json.dumps(record, ensure_ascii=False) + "\n")

            log(f"SAVED {local_path}", log_file)

            time.sleep(PAUSE)

    log("", log_file)
    log("Download finished", log_file)
    log(f"downloaded: {downloaded}", log_file)
    log(f"duplicates: {duplicates}", log_file)
    log(f"errors: {errors}", log_file)

    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
