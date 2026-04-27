# Bay Area Childcare Violations & Complaints

A public transparency site showing complaints and violations for childcare facilities in San Francisco, Alameda, San Mateo, and Santa Clara counties. Data is sourced from the California Department of Social Services Community Care Licensing Division (CCLD).

## What it shows

- Type A violations (immediate health/safety risk) and Type B violations (corrective action required)
- Complaint history with substantiation findings
- Full complaint and inspection report text fetched live from the CCLD API

## Updating the data

Requires Python 3:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python fetch_data.py --county "San Francisco" "Alameda" "San Mateo" "Santa Clara"
```

### How caching works

The script warm-starts from the existing `data/facilities.json` on every run. Facilities already present in that file are skipped — only newly discovered facility numbers are fetched. This makes incremental updates fast (a few minutes rather than ~20 minutes for a full run).

| Flag | Behavior |
|------|----------|
| _(none)_ | Skip facilities already in `data/facilities.json`; fetch only new ones |
| `--resume` | Also skip facilities saved in `data/cache.json` from an interrupted run |
| `--full` | Ignore `data/facilities.json` and re-fetch everything from scratch (~20 min) |

If a run is interrupted, re-run with `--resume` to continue from the checkpoint:

```bash
python fetch_data.py --county "San Francisco" "Alameda" "San Mateo" "Santa Clara" --resume
```

To re-fetch all data from scratch (e.g. to pick up updated violation counts):

```bash
python fetch_data.py --county "San Francisco" "Alameda" "San Mateo" "Santa Clara" --full
```

## Data source

Violations and complaints are sourced from the California Department of Social Services, Community Care Licensing Division (CCLD) Transparency API.

Small family child care homes (type 0) are excluded from the CCLD search API. Their facility numbers are discovered separately from the [CA CHHS Open Data Portal](https://data.chhs.ca.gov/dataset/community-care-licensing-facilities) and detail records are then fetched individually from CCLD.

Records are public information. This site is not affiliated with or endorsed by the State of California.

## License

MIT — see [LICENSE](LICENSE).
