#!/usr/bin/env python3

"""
STEP 0C
Repository discovery

Scans domains for academic repository systems
(DSpace, EPrints, OAI-PMH, OJS)

Input:
    seeds/seed_domains_curated.txt

Output:
    seeds/repositories.yaml
    seeds/repository_seeds.txt
"""

from pathlib import Path
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "seeds"

DOMAIN_FILE = SEEDS / "seed_domains_curated.txt"

OUT_REPO = SEEDS / "repositories.yaml"
OUT_SEEDS = SEEDS / "repository_seeds.txt"

TIMEOUT = 10


REPO_PATTERNS = {
    "dspace": [
        "/xmlui",
        "/jspui",
        "/handle/",
        "/bitstream/"
    ],
    "eprints": [
        "/eprint",
        "/id/eprint",
        "/cgi/search"
    ],
    "oai_pmh": [
        "/oai",
        "?verb=Identify"
    ],
    "ojs": [
        "/index.php",
        "/article/view",
        "/issue/view"
    ]
}


def load_domains():

    if not DOMAIN_FILE.exists():
        return []

    with open(DOMAIN_FILE) as f:
        return [x.strip() for x in f if x.strip()]


def check_url(url):

    try:
        r = requests.get(url, timeout=TIMEOUT)

        if r.status_code == 200:
            return True

    except:
        pass

    return False


def detect_repository(domain):

    base = f"https://{domain}"

    for repo_type, patterns in REPO_PATTERNS.items():

        for p in patterns:

            url = base + p

            if check_url(url):
                return repo_type, url

    return None, None


def main():

    domains = load_domains()

    repositories = []
    repo_seeds = []

    for d in domains:

        repo_type, url = detect_repository(d)

        if repo_type:

            repositories.append({
                "domain": d,
                "type": repo_type,
                "entry": url
            })

            repo_seeds.append(url)

            print("Repository found:", repo_type, url)

    OUT_REPO.write_text(yaml.dump(repositories))
    OUT_SEEDS.write_text("\n".join(repo_seeds))

    print()
    print("Repositories discovered:", len(repositories))


if __name__ == "__main__":
    main()
