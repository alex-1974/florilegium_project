#!/usr/bin/env bash
set -euo pipefail

OLD_ROOT="$HOME/Programmiersprachen/Blender/bvillage_project/research/literature_pipeline"
NEW_ROOT="$HOME/Programmiersprachen/Python/florilegium_project"

echo "==> Prüfe Quellprojekt"
test -d "$OLD_ROOT"

echo "==> Lege Zielprojekt an"
mkdir -p "$NEW_ROOT"
cd "$NEW_ROOT"

echo "==> Lege neue Projektstruktur an"
mkdir -p \
  src/florilegium/{models,crawl,classify,pdf,score,output,logging,seeds,utils,profiles} \
  workflows \
  config/profiles \
  seeds \
  var/{cache/{http,pages,search},data,downloads,logs} \
  tests/{unit,integration,fixtures} \
  legacy/{crawler,semantics,scripts}

echo "==> Lege Paketdateien an"
touch \
  src/florilegium/__init__.py \
  src/florilegium/cli.py \
  src/florilegium/settings.py \
  src/florilegium/config.py \
  src/florilegium/models/__init__.py \
  src/florilegium/crawl/__init__.py \
  src/florilegium/classify/__init__.py \
  src/florilegium/pdf/__init__.py \
  src/florilegium/score/__init__.py \
  src/florilegium/output/__init__.py \
  src/florilegium/logging/__init__.py \
  src/florilegium/seeds/__init__.py \
  src/florilegium/utils/__init__.py \
  src/florilegium/profiles/__init__.py

echo "==> Übernehme README"
if [ -f "$OLD_ROOT/README.md" ]; then
  cp "$OLD_ROOT/README.md" "$NEW_ROOT/README.md"
else
  touch "$NEW_ROOT/README.md"
fi

echo "==> Übernehme Konfiguration"
if [ -d "$OLD_ROOT/config" ]; then
  rsync -a "$OLD_ROOT/config/" "$NEW_ROOT/config/"
fi

echo "==> Übernehme Seeds"
if [ -d "$OLD_ROOT/seeds" ]; then
  rsync -a "$OLD_ROOT/seeds/" "$NEW_ROOT/seeds/"
fi

echo "==> Übernehme Laufdaten nach var/"
if [ -d "$OLD_ROOT/cache" ]; then
  rsync -a "$OLD_ROOT/cache/" "$NEW_ROOT/var/cache/"
fi

if [ -d "$OLD_ROOT/data" ]; then
  mkdir -p "$NEW_ROOT/var/data"
  find "$OLD_ROOT/data" -maxdepth 1 -type f \( -name "*.csv" -o -name "*.tsv" -o -name "*.txt" \) -exec cp {} "$NEW_ROOT/var/data/" \;
  find "$OLD_ROOT/data" -maxdepth 1 -type f -name "*.log" -exec cp {} "$NEW_ROOT/var/logs/" \;
fi

if [ -d "$OLD_ROOT/downloads" ]; then
  rsync -a "$OLD_ROOT/downloads/" "$NEW_ROOT/var/downloads/"
fi

if [ -d "$OLD_ROOT/logs" ]; then
  rsync -a "$OLD_ROOT/logs/" "$NEW_ROOT/var/logs/"
fi

echo "==> Sichere Altmodule in legacy/"
if [ -d "$OLD_ROOT/crawler" ]; then
  rsync -a "$OLD_ROOT/crawler/" "$NEW_ROOT/legacy/crawler/"
fi

if [ -d "$OLD_ROOT/semantics" ]; then
  rsync -a "$OLD_ROOT/semantics/" "$NEW_ROOT/legacy/semantics/"
fi

if [ -d "$OLD_ROOT/scripts" ]; then
  rsync -a "$OLD_ROOT/scripts/" "$NEW_ROOT/legacy/scripts/"
fi

echo "==> Kopiere bestehende Kernmodule an ihre neue Zielposition"

# crawl
[ -f "$OLD_ROOT/crawler/frontier.py" ] && cp "$OLD_ROOT/crawler/frontier.py" "$NEW_ROOT/src/florilegium/crawl/frontier.py"
[ -f "$OLD_ROOT/crawler/page_fetcher.py" ] && cp "$OLD_ROOT/crawler/page_fetcher.py" "$NEW_ROOT/src/florilegium/crawl/page_fetcher.py"

# classify
[ -f "$OLD_ROOT/crawler/html_classifier.py" ] && cp "$OLD_ROOT/crawler/html_classifier.py" "$NEW_ROOT/src/florilegium/classify/html_classifier.py"
[ -f "$OLD_ROOT/crawler/path_semantics.py" ] && cp "$OLD_ROOT/crawler/path_semantics.py" "$NEW_ROOT/src/florilegium/classify/path_semantics.py"
[ -f "$OLD_ROOT/crawler/keyword_extractor.py" ] && cp "$OLD_ROOT/crawler/keyword_extractor.py" "$NEW_ROOT/src/florilegium/classify/keyword_extractor.py"

# pdf
[ -f "$OLD_ROOT/crawler/pdf_verify.py" ] && cp "$OLD_ROOT/crawler/pdf_verify.py" "$NEW_ROOT/src/florilegium/pdf/verify.py"

# score
[ -f "$OLD_ROOT/crawler/scoring.py" ] && cp "$OLD_ROOT/crawler/scoring.py" "$NEW_ROOT/src/florilegium/score/scoring.py"
[ -f "$OLD_ROOT/crawler/domain_reputation.py" ] && cp "$OLD_ROOT/crawler/domain_reputation.py" "$NEW_ROOT/src/florilegium/score/domain_reputation.py"
[ -f "$OLD_ROOT/crawler/domain_stats.py" ] && cp "$OLD_ROOT/crawler/domain_stats.py" "$NEW_ROOT/src/florilegium/score/domain_stats.py"
[ -f "$OLD_ROOT/crawler/semantic_ranker.py" ] && cp "$OLD_ROOT/crawler/semantic_ranker.py" "$NEW_ROOT/src/florilegium/score/semantic_ranker.py"

# logging
[ -f "$OLD_ROOT/crawler/run_logger.py" ] && cp "$OLD_ROOT/crawler/run_logger.py" "$NEW_ROOT/src/florilegium/logging/run_logger.py"

# utils
[ -f "$OLD_ROOT/crawler/url_norm.py" ] && cp "$OLD_ROOT/crawler/url_norm.py" "$NEW_ROOT/src/florilegium/utils/url_norm.py"

# semantics extras
[ -f "$OLD_ROOT/semantics/sbert_ranker.py" ] && cp "$OLD_ROOT/semantics/sbert_ranker.py" "$NEW_ROOT/src/florilegium/score/semantic_ranker_sbert.py"
[ -f "$OLD_ROOT/semantics/structural_bm25.py" ] && cp "$OLD_ROOT/semantics/structural_bm25.py" "$NEW_ROOT/src/florilegium/score/structural_bm25.py"
[ -f "$OLD_ROOT/semantics/structural_bm25_ranker.py" ] && cp "$OLD_ROOT/semantics/structural_bm25_ranker.py" "$NEW_ROOT/src/florilegium/score/structural_bm25_ranker.py"

echo "==> Übernehme Workflows aus scripts in neue Namen"
[ -f "$OLD_ROOT/scripts/step1_crawler.py" ] && cp "$OLD_ROOT/scripts/step1_crawler.py" "$NEW_ROOT/workflows/crawl.py"
[ -f "$OLD_ROOT/scripts/step2_download_pdfs.py" ] && cp "$OLD_ROOT/scripts/step2_download_pdfs.py" "$NEW_ROOT/workflows/download.py"
[ -f "$OLD_ROOT/scripts/step3_pdf_audit.py" ] && cp "$OLD_ROOT/scripts/step3_pdf_audit.py" "$NEW_ROOT/workflows/audit.py"
[ -f "$OLD_ROOT/scripts/step0_seed_enrichment.py" ] && cp "$OLD_ROOT/scripts/step0_seed_enrichment.py" "$NEW_ROOT/workflows/seed_enrichment.py"
[ -f "$OLD_ROOT/scripts/step0b_seed_filter.py" ] && cp "$OLD_ROOT/scripts/step0b_seed_filter.py" "$NEW_ROOT/workflows/seed_filter.py"
[ -f "$OLD_ROOT/scripts/step0c_repository_discovery.py" ] && cp "$OLD_ROOT/scripts/step0c_repository_discovery.py" "$NEW_ROOT/workflows/repository_discovery.py"

echo "==> Lege minimales pyproject.toml an"
cat > "$NEW_ROOT/pyproject.toml" <<'EOF'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "florilegium"
version = "0.1.0"
description = "Scientific discovery and retrieval crawler"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
florilegium = "florilegium.cli:main"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
EOF

echo "==> Lege minimale CLI an"
cat > "$NEW_ROOT/src/florilegium/cli.py" <<'EOF'
from __future__ import annotations

import sys


def main() -> int:
    print("Florilegium CLI placeholder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
EOF

echo "==> Lege .gitignore an"
cat > "$NEW_ROOT/.gitignore" <<'EOF'
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
var/cache/
var/logs/
var/data/
var/downloads/
EOF

echo "==> Ergebnisstruktur"
tree -a -I '__pycache__|*.pyc|.venv' "$NEW_ROOT" || true

echo
echo "Fertig."
echo "Neues Projekt: $NEW_ROOT"
