# Bay Area Childcare Violations & Complaints

A public transparency site showing complaints and violations for childcare facilities in San Francisco, Marin, Alameda, San Mateo, and Santa Clara counties. Data is sourced from the California Department of Social Services Community Care Licensing Division (CCLD).

## What it shows

- Type A violations (immediate health/safety risk) and Type B violations (corrective action required)
- Complaint history with substantiation findings
- Full complaint and inspection report text fetched live from the CCLD API

## Updating the data

### First-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
```

### Regular refresh

Run this periodically (e.g. monthly) to pick up updated violations, complaints, and newly licensed facilities including small family child care homes:

```bash
source .venv/bin/activate
python fetch_data.py --county "San Francisco" "Marin" "Alameda" "San Mateo" "Santa Clara" --full --enumerate-gaps
```

This takes ~50 minutes.

### Other options

| Flag | Behavior |
|------|----------|
| _(none)_ | Skip facilities already in `data/facilities.json`; only fetch newly discovered ones. Useful if you just want to quickly add a specific county or facility type without re-fetching everything. |
| `--enumerate-gaps` | Also scan numeric gaps to find privacy-protected small FCCHs (~30 min extra) |
| `--resume` | Continue an interrupted run from the checkpoint file |
| `--full` | Re-fetch all facilities from scratch (~20 min, required to pick up updated violation/complaint counts) |

If a run is interrupted, re-run with `--resume`:

```bash
python fetch_data.py --county "San Francisco" "Marin" "Alameda" "San Mateo" "Santa Clara" --resume
```

## Data source

Violations and complaints are sourced from the California Department of Social Services, Community Care Licensing Division (CCLD) Transparency API.

Small family child care homes (type 0) are excluded from the CCLD search API and absent from public bulk downloads due to privacy protections. They are discovered via two methods: supplemental data from the [CA CHHS Open Data Portal](https://data.chhs.ca.gov/dataset/community-care-licensing-facilities), and numeric gap enumeration (`--enumerate-gaps`) which scans the gaps between known facility numbers to find unlisted homes.

Records are public information. This site is not affiliated with or endorsed by the State of California.

## License

MIT — see [LICENSE](LICENSE).
