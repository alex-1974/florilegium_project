# literature_pipeline

## Step 1

Collect candidate PDF links, verify them, cache search and HTTP metadata, and write CSV manifests.

### Run

```bash
cd literature_pipeline
python3 scripts/step1_collect_verify_links.py
```

### Config

Edit `config/queries.yaml`.

### Outputs

- `data/links_raw.csv`
- `data/links_verified.csv`
- `cache/search/`
- `cache/http/`
- `logs/step1_summary.json`
