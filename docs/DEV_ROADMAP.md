# Florilegium Development Roadmap

This document lists the major remaining tasks for Florilegium.

The current state is a working minimal crawler pipeline.

---

# Current Status

Completed:

- extraction from BVILLAGE project
- standalone Python project
- CLI interface
- runtime path management
- crawl → download → audit pipeline
- project directory structure
- runtime directory separation (var/)

---

# Priority 1 — Core Architecture

## Generalize crawler beyond architecture

Current scoring and audit rules contain architecture-specific keywords.

Tasks:

- move domain-specific keyword sets into profiles
- create profile system

Example structure:

profiles/
    base.py
    historical_architecture.py
    medicine.py

---

## Profile-based crawling

Allow topic-specific crawling behavior.

Example:

florilegium crawl --profile historical_architecture

---

# Priority 2 — Crawler Improvements

- adaptive domain reputation learning
- improved repository detection
- better link classification

---

# Priority 3 — PDF Processing

- improve PDF verification
- optional OCR support
- full text indexing

---

# Priority 4 — Research Workflow Features

- literature deduplication
- citation extraction
- author detection
- metadata enrichment

---

# Priority 5 — Performance

- parallel crawling
- parallel downloads
- large-scale crawl stability

---

# Long-term Vision

Florilegium should become a general scientific literature discovery system
for building large research corpora across many scientific disciplines.
