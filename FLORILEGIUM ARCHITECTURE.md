# FLORILEGIUM_ARCHITECTURE.md

## 1. Mission

**Florilegium** ist ein wissenschaftlicher Discovery- und Retrieval-Crawler.

Sein Ziel ist es, **wissenschaftliche Quellen automatisiert zu finden, zu bewerten und zu katalogisieren**.

Dabei soll Florilegium:

- thematische Literatur im Web entdecken
- wissenschaftliche Dokumente identifizieren
- Repositorien und Archive durchsuchen
- PDFs und andere Quellen verifizieren
- Relevanz modellieren
- eine kuratierbare Forschungsbibliothek erzeugen

Florilegium ist **domänenneutral** und kann für beliebige wissenschaftliche Themen eingesetzt werden, z. B.:

- Medizin
- Geschichte
- Architekturgeschichte
- Militärgeschichte
- Technikgeschichte
- Sozialwissenschaft
- Naturwissenschaft

Ein konkretes Forschungsprojekt (z. B. BVILLAGE) ist **nur ein Konsument** der erzeugten Literaturdaten.

---

# 2. Grundprinzipien

## 2.1 Domänenneutraler Kern

Der Florilegium-Kern enthält ausschließlich **themenunabhängige Logik**:

- Crawling
- HTML-Analyse
- Link-Extraktion
- Dokumentverifikation
- Scoring
- Domain-Reputation
- Ranking
- Datenpersistenz

Der Kern kennt **keine Fachbegriffe** eines bestimmten wissenschaftlichen Feldes.

---

## 2.2 Topic Profiles

Fachliche Spezialisierung erfolgt über **Topic Profiles**.

Ein Topic Profile definiert:

- Themenbegriffe
- Synonyme
- Negativbegriffe
- relevante Domains
- bekannte Repositorien
- Journals
- typische Dokumenttypen
- Prioritätsgewichte
- Domain-Heuristiken

Beispiele:

profiles/
    medicine
    historical_architecture
    military_history
    epidemiology

Ein Profil enthält nur **Daten und Konfiguration**, keine Engine-Logik.

---

## 2.3 Discovery-First-Ansatz

Florilegium beginnt nicht direkt mit Crawling.

Zuerst werden **Seed-Quellen entdeckt**.

Discovery kann erfolgen über:

- Wikipedia
- Wikidata
- bekannte Repositorien
- Journals
- wissenschaftliche Institutionen
- Domain-Discovery
- Entitätsnetzwerke

Diese Discovery-Schicht ist ein zentraler Bestandteil des Systems.

---

## 2.4 Evidence-based Ranking

Florilegium bewertet Dokumente anhand mehrerer Signale:

### Dokumentebene

- PDF-Verifikation
- Dokumenttyp
- Metadaten
- Seitenstruktur

### Kontext

- Link-Kontext
- Abschnittsüberschriften
- Seitentyp

### Semantik

- Keyword-Match
- semantische Ähnlichkeit
- Topic-Relevanz

### Quelle

- Domain-Reputation
- Repository-Signale
- Institutionstyp

Alle Signale fließen in ein **hybrides Score-Modell**.

---

# 3. Systemarchitektur

Florilegium besteht aus sechs Hauptschichten.

Discovery Layer  
Seed Layer  
Crawl Layer  
Classification Layer  
Scoring Layer  
Output / Library Layer

---

# 4. Discovery Layer

Der Discovery Layer erzeugt neue Seeds.

Typische Quellen:

### Wikipedia

Wikipedia-Artikel liefern:

- thematische Einstiegspunkte
- Literaturverzeichnisse
- externe Links
- Institutionen
- Archive
- Forschungsprojekte

### Wikidata

Wikidata liefert strukturierte Entitäten:

- Personen
- Institutionen
- Werke
- Journals
- Archive
- Orte
- Themen

Diese Entitäten können Seeds erweitern.

### Repository Discovery

Florilegium erkennt typische Repositorien:

- DSpace
- EPrints
- Fedora
- IIIF Viewer
- Library Catalogues
- Digital Collections

### Journal Discovery

Identifikation wissenschaftlicher Journals über:

- Crossref
- DOAJ
- Publisherseiten
- Bibliographien

---

# 5. Seed Layer

Seeds sind Ausgangspunkte für Crawling.

Typische Seed-Typen:

- seed_urls
- repository_seeds
- journal_seeds
- domain_seeds
- entity_seeds

Seeds können aus mehreren Quellen stammen:

- manuell
- Discovery
- Wikipedia
- Wikidata
- Literaturverzeichnisse

Seeds werden vor dem Crawl gefiltert und bewertet.

---

# 6. Crawl Layer

Der Crawl Layer navigiert Webseiten.

Aufgaben:

- HTML abrufen
- Seitentyp bestimmen
- Links extrahieren
- Frontier verwalten
- Crawl-Budget kontrollieren

Zentrale Komponenten:

- frontier
- scheduler
- page_fetcher
- link_extractor
- expand_policy

---

# 7. Classification Layer

Webseiten werden entlang mehrerer Achsen klassifiziert.

### Seitentyp

- publication
- repository
- heritage
- bibliography
- teaching
- news
- admin
- navigation

### Dokumenttyp

- article
- monograph
- report
- thesis
- scan
- dataset
- guideline

### Repository-Typ

- journal platform
- institutional repository
- digital archive
- library catalogue

---

# 8. Document Verification

Dokumente werden vor Aufnahme überprüft.

Typische Prüfungen:

- PDF-Header
- MIME-Type
- Dateigröße
- Download-Endpoint
- Redirect-Analyse

Ziel: falsche Kandidaten früh aussortieren.

---

# 9. Scoring Layer

Das Score-Modell kombiniert mehrere Signale:

- cosine_score
- context_score
- url_score
- filename_score
- path_score
- domain_score
- repository_score
- scientific_score
- semantic_score
- spam_risk
- confidence

Das Ergebnis ist eine Entscheidung:

- accept
- maybe
- review
- reject

---

# 10. Domain Reputation

Florilegium lernt aus vergangenen Entscheidungen.

Für jede Domain werden gespeichert:

- html_seen
- pdf_checked
- verify_fail
- accepted
- rejected

Daraus entstehen:

- Reputation
- Erfolgsrate
- Crawl-Priorität

---

# 11. Output Layer

Florilegium erzeugt mehrere Artefakte.

### Kandidaten

pdf_candidates_all.csv

### Crawl-Analyse

- html_decisions.csv
- domain_reputation_summary.csv

### Review-Daten

- review_candidates.csv
- reject_candidates.csv

Diese Outputs bilden eine **kuratierbare Literaturbasis**.

---

# 12. Workflows

Florilegium organisiert seine Arbeit über Workflows.

### Discovery

florilegium discover seeds  
florilegium discover repositories  
florilegium discover journals  

### Crawl

florilegium crawl

### Download

florilegium download

### Audit

florilegium audit

---

# 13. Projektstruktur

Florilegium folgt einem **src-Layout**.

florilegium_project/
    src/florilegium/
    config/
    seeds/
    var/
    tests/

Code liegt ausschließlich unter:

src/florilegium/

Laufdaten unter:

var/

---

# 14. Relationship to Other Projects

Florilegium ist **kein projektspezifischer Crawler**.

Andere Projekte (z. B. BVILLAGE) nutzen Florilegium lediglich als:

literature discovery engine

Sie konsumieren:

- PDF-Sammlungen
- Literaturdatenbanken
- Metadaten
- Rankings

Florilegium bleibt unabhängig.

---

# 15. Design Goals

Florilegium soll langfristig:

- robust gegen Web-Noise sein
- wissenschaftliche Inhalte priorisieren
- neue Repositorien entdecken
- thematisch generalisierbar sein
- reproduzierbare Forschungsbibliotheken erzeugen

---

# Fazit

Florilegium ist keine einfache Webcrawler-Pipeline.

Es ist eine **wissenschaftliche Discovery-Engine**, die:

- Themenräume erschließt
- Quellen sammelt
- Dokumente bewertet
- Literaturbibliotheken aufbaut.
