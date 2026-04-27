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
python fetch_data.py
```

To refresh a subset:

```bash
python fetch_data.py --county "San Francisco"
python fetch_data.py --resume   # continue an interrupted run
```

## Data source

All data is sourced from the California Department of Social Services, Community Care Licensing Division. Records are public information. This site is not affiliated with or endorsed by the State of California.

## License

MIT — see [LICENSE](LICENSE).
