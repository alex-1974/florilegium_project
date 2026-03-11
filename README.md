# Florilegium

Florilegium is a scientific literature discovery and collection tool.

It crawls academic websites, repositories and publication pages,
discovers PDF documents, downloads them, and performs a first-pass
relevance audit.

The goal is to support large-scale literature research workflows
in any scientific field.

Florilegium was originally developed to support historical
architecture research but is now designed as a general-purpose
academic literature crawler.

---

# Core Capabilities

Florilegium currently provides three pipeline steps:

## 1. Crawl

Discover PDF documents by crawling seed websites.

The crawler:

- classifies HTML pages
- evaluates link context
- verifies PDF candidates
- scores PDF candidates
- records domain reputation
- produces candidate lists

Output:

var/data/pdf_links.csv

Run:

florilegium crawl

---

## 2. Download

Downloads verified PDF candidates.

Features:

- SHA256 deduplication
- per-domain storage
- download logging
- status tracking

Output:

var/downloads/
var/data/pdf_downloads.csv
var/data/pdf_downloads.jsonl

Run:

florilegium download

---

## 3. Audit

Performs a lightweight text analysis of downloaded PDFs.

Purpose:

- estimate crawler precision
- detect noise sources
- classify documents

Output:

var/data/pdf_audit.csv

Run:

florilegium audit

---

# Project Structure

florilegium_project/

├─ src/florilegium/
│  ├─ classify/
│  ├─ pdf/
│  ├─ score/
│  ├─ workflows/
│  ├─ logging/
│  ├─ settings.py
│  └─ cli.py
│
├─ config/
├─ seeds/
│
├─ var/
│  ├─ cache/
│  ├─ data/
│  ├─ downloads/
│  └─ logs/
│
└─ workflows/

Runtime data is stored in var/ to keep the source tree clean.
