#!/usr/bin/env python3
"""
Fetch California childcare center complaints and violations from CCLD API.
Saves to data/facilities.json for use by the transparency website.

Usage:
    python fetch_data.py              # fetch all childcare types, all counties
    python fetch_data.py --county "Los Angeles"  # single county for testing
    python fetch_data.py --resume     # skip already-cached details
"""

import requests
import json
import csv
import io
import time
import os
import sys
import argparse
from datetime import datetime

BASE_URL = "https://www.ccld.dss.ca.gov/transparencyapi/api"
# CA CHHS open data resource for small FCCHs — CCLD search API returns HTTP 400 for type 0
CHHS_SMALL_FCCH_RESOURCE = "4b5cc48d-03b1-4f42-a7d1-b9816903eb2b"
HEADERS = {
    "DSS-Transparency-Config": json.dumps({
        "Version": "11.18.0R",
        "deviceReady": 1,
        "GUID": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "DocProtocol": "https://"
    }),
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.ccld.dss.ca.gov/carefacilitysearch/",
}

# API caps results at 250 per search; these large counties need city-level breakdown
LARGE_COUNTIES = {"Los Angeles", "San Diego", "Orange", "Riverside", "San Bernardino",
                  "Santa Clara", "Alameda", "Sacramento", "Contra Costa", "Fresno",
                  "Kern", "San Francisco", "Ventura"}

RATE_LIMIT = 0.15
CACHE_FILE = "data/cache.json"
CLOSED_FILE = "data/closed.json"
CAP = 250  # API result cap per query


def is_closed(status):
    s = (status or "").strip().lower()
    return s.startswith("closed") or s == "inactive"


def get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r


def get_childcare_types():
    data = get(f"{BASE_URL}/Group/").json()
    for group in data:
        if group.get("id") == "ChildCare":
            return [
                {"id": t["id"], "name": t["display_name"]}
                for t in group.get("facility_type", [])
                if t["id"] != 0  # type 0 returns 400 errors
            ]
    return []


def get_counties():
    return [c["County"] for c in get(f"{BASE_URL}/CACounty").json() if c.get("County")]


def search(fac_type_id, county="", city="", zip_code=""):
    try:
        r = get(f"{BASE_URL}/FacilitySearch", params={
            "facType": fac_type_id,
            "facility": "", "Street": "",
            "city": city, "zip": zip_code,
            "county": county, "facnum": ""
        })
        return r.json().get("FACILITYARRAY", [])
    except Exception as e:
        print(f"  WARN search type={fac_type_id} county={county!r} city={city!r} zip={zip_code!r}: {e}", file=sys.stderr)
        return []



def get_small_fcch_numbers(counties):
    """Discover small FCCH facility numbers from two bulk sources combined.

    The CCLD Transparency API rejects facType=0 (small family child care homes)
    with HTTP 400. We use the union of:
      1. CCLD bulk download (DownloadStateData/CHILDCAREHOMEmorethan8)
      2. CA CHHS open data portal CSV
    because each source contains facilities the other omits.
    """
    upper_counties = {c.upper() for c in counties} if counties else None
    results = {}

    def add_row(fnum, name, address, city, zipcode, status, county):
        if fnum and fnum not in results:
            results[fnum] = {
                "FACILITYNUMBER": fnum,
                "FACILITYNAME": name,
                "STREETADDRESS": address,
                "CITY": city,
                "ZIPCODE": zipcode,
                "STATUS": status,
                "COUNTY": county,
            }

    # Source 1: CCLD bulk download
    print("  [Family Child Care Home(Small)] — fetching from CCLD bulk download…")
    try:
        r = requests.get(
            f"{BASE_URL}/DownloadStateData/CHILDCAREHOMEmorethan8",
            headers=HEADERS, timeout=120,
        )
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            county = row.get("County Name", "").strip()
            if upper_counties and county.upper() not in upper_counties:
                continue
            add_row(
                row.get("Facility Number", "").strip(),
                row.get("Facility Name", "").strip(),
                row.get("Facility Address", "").strip(),
                row.get("Facility City", "").strip(),
                row.get("Facility Zip", "").strip(),
                row.get("Facility Status", "").strip(),
                county,
            )
        print(f"    → {len(results)} from CCLD bulk")
    except Exception as e:
        print(f"  WARN: CCLD bulk download failed: {e}", file=sys.stderr)

    before = len(results)

    # Source 2: CA CHHS open data (supplements CCLD — each source has unique entries)
    print("  [Family Child Care Home(Small)] — supplementing from CA CHHS open data…")
    try:
        meta = requests.get(
            f"https://data.chhs.ca.gov/api/3/action/resource_show?id={CHHS_SMALL_FCCH_RESOURCE}",
            timeout=15,
        )
        meta.raise_for_status()
        url = meta.json()["result"]["url"]
        r2 = requests.get(url, timeout=120)
        r2.raise_for_status()
        for row in csv.DictReader(io.StringIO(r2.text)):
            county = row.get("county_name", "").strip()
            if upper_counties and county.upper() not in upper_counties:
                continue
            add_row(
                row.get("facility_number", "").strip(),
                row.get("facility_name", "").strip(),
                row.get("facility_address", "").strip(),
                row.get("facility_city", "").strip(),
                row.get("facility_zip", "").strip(),
                row.get("facility_status", "").strip(),
                county,
            )
        print(f"    → {len(results) - before} additional from CHHS open data")
    except Exception as e:
        print(f"  WARN: CHHS open data fetch failed: {e}", file=sys.stderr)

    return results


def discover_facilities(childcare_types, counties):
    """Phase 1: collect all unique facility numbers via search."""
    all_facilities = {}  # fac_num -> {basic, type}
    total_searches = 0

    for ftype in childcare_types:
        type_id, type_name = ftype["id"], ftype["name"]
        print(f"\n  [{type_name}]")

        for county in counties:
            results = search(type_id, county=county)
            time.sleep(RATE_LIMIT)
            total_searches += 1

            at_cap = len(results) == CAP

            for f in results:
                fnum = f.get("FACILITYNUMBER")
                if fnum and fnum not in all_facilities:
                    all_facilities[fnum] = {"basic": f, "type": type_name}

            # If we hit the cap on a large county, drill down by zip code
            if at_cap and county in LARGE_COUNTIES:
                zip_codes = list({f.get("ZIPCODE", "").strip() for f in results if f.get("ZIPCODE", "").strip()})
                print(f"    {county}: hit cap ({CAP}), drilling by {len(zip_codes)} zip codes…")
                for zip_code in zip_codes:
                    zip_results = search(type_id, county=county, zip_code=zip_code)
                    time.sleep(RATE_LIMIT)
                    total_searches += 1
                    for f in zip_results:
                        fnum = f.get("FACILITYNUMBER")
                        if fnum and fnum not in all_facilities:
                            all_facilities[fnum] = {"basic": f, "type": type_name}
                    if len(zip_results) == CAP:
                        print(f"      ZIP {zip_code}: still capped at {CAP} — some facilities may be missed")

        count = sum(1 for v in all_facilities.values() if v["type"] == type_name)
        print(f"    → {count} unique facilities so far this type")

    print(f"\n  Total unique facilities discovered: {len(all_facilities)} ({total_searches} searches)")

    small_fcch = get_small_fcch_numbers(counties)
    added = 0
    for fnum, basic in small_fcch.items():
        if fnum not in all_facilities:
            all_facilities[fnum] = {"basic": basic, "type": "Family Child Care Home(Small)"}
            added += 1
    print(f"  + {added} small FCCHs added ({len(small_fcch)} in region, {len(small_fcch)-added} already known)")
    print(f"  Grand total: {len(all_facilities)} facilities")
    return all_facilities


def get_detail(fac_num):
    try:
        return get(f"{BASE_URL}/FacilityDetail/{fac_num}").json()
    except Exception as e:
        print(f"  WARN detail {fac_num}: {e}", file=sys.stderr)
        return None


def parse_date(s):
    if not s or not s.strip():
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_date_list(s):
    return [d for d in (parse_date(p) for p in (s or "").split(",")) if d]


def complaint_submitted_date(control_number):
    """Control numbers encode submission date: XX-CC-YYYYMMDDHHMMSS."""
    if not control_number:
        return None
    parts = control_number.split("-")
    for p in parts:
        if len(p) >= 8 and p[:4].isdigit():
            try:
                return datetime.strptime(p[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def process(basic, type_name, detail):
    fd = detail.get("FacilityDetail", {})

    complaints = []
    all_dates = []
    for c in (fd.get("COMPLAINTARRAY") or []):
        if not c:
            continue
        ctrl = c.get("CONTROLNUMBER")
        sub = complaint_submitted_date(ctrl)
        visits = parse_date_list(c.get("CMPVISITDATES", ""))
        approved = parse_date(c.get("APPROVEDATE"))
        sub_count = int(c.get("SUBALLEGATIONS") or 0)
        type_a_cit = int(c.get("CITTYPEA") or 0)
        type_b_cit = int(c.get("CITTYPEB") or 0)

        if sub_count > 0:
            finding = "Substantiated"
        elif int(c.get("UNSALLEGATIONS") or 0) > 0:
            finding = "Unsubstantiated"
        elif int(c.get("INCALLEGATIONS") or 0) > 0:
            finding = "Inconclusive"
        else:
            finding = "Pending"

        status = "Closed" if approved else "Open"

        complaints.append({
            "control_number": ctrl,
            "submitted_date": sub,
            "approved_date": approved,
            "visit_dates": visits,
            "status": status,
            "finding": finding,
            "substantiated_allegations": sub_count,
            "unsubstantiated_allegations": int(c.get("UNSALLEGATIONS") or 0),
            "type_a_citations": type_a_cit,
            "type_b_citations": type_b_cit,
        })
        if sub: all_dates.append(sub)
        if approved: all_dates.append(approved)
        all_dates += visits

    last_visit = parse_date(fd.get("LASTVISITDATE"))
    if last_visit: all_dates.append(last_visit)

    # Match CCLD's own calculation: complaint + inspection + other visit citations
    insp_a  = int(fd.get("NBRINSPTYPA") or 0)
    insp_b  = int(fd.get("NBRINSPTYPB") or 0)
    other_a = int(fd.get("NBROTHERTYPA") or 0)
    other_b = int(fd.get("NBROTHERTYPB") or 0)
    type_a  = int(fd.get("TOTTYPEA") or 0) + insp_a + other_a
    type_b  = int(fd.get("TOTTYPEB") or 0) + insp_b + other_b

    insp_dates  = parse_date_list(fd.get("VSTDATEINSP", ""))
    other_dates = parse_date_list(fd.get("VSTDATEOTHER", ""))

    inspections = []
    if insp_a or insp_b:
        inspections.append({
            "visit_type": "Inspection",
            "visit_dates": insp_dates,
            "type_a_citations": insp_a,
            "type_b_citations": insp_b,
        })
    if other_a or other_b:
        inspections.append({
            "visit_type": "Other Visit",
            "visit_dates": other_dates,
            "type_a_citations": other_a,
            "type_b_citations": other_b,
        })

    return {
        "number": fd.get("FACILITYNUMBER") or basic.get("FACILITYNUMBER"),
        "name": (fd.get("FACILITYNAME") or basic.get("FACILITYNAME") or "").strip(),
        "address": (fd.get("STREETADDRESS") or basic.get("STREETADDRESS") or "").strip(),
        "city": (fd.get("CITY") or basic.get("CITY") or "").strip(),
        "zip": fd.get("ZIPCODE") or basic.get("ZIPCODE"),
        "county": (fd.get("COUNTY") or basic.get("COUNTY") or "").strip().title(),
        "status": fd.get("STATUS") or basic.get("STATUS") or "",
        "type": type_name,
        "capacity": fd.get("CAPACITY"),
        "phone": fd.get("TELEPHONE"),
        "licensee": fd.get("LICENSEENAME"),
        "license_effective_date": parse_date(fd.get("LICENSEEFFECTIVEDATE")),
        "last_visit": last_visit,
        "type_a_violations": type_a,
        "type_b_violations": type_b,
        "total_violations": type_a + type_b,
        "total_complaints": int(fd.get("CMPCOUNT") or len(complaints)),
        "substantiated_complaints": sum(
            1 for c in complaints if c.get("finding") == "Substantiated"
        ),
        "complaints": complaints,
        "inspections": inspections,
        "most_recent_activity": max(all_dates) if all_dates else None,
        "district_office": fd.get("DISTRICTOFFICE"),
    }


def load_existing():
    """Load already-fetched facilities from data/facilities.json as a warm cache."""
    try:
        with open("data/facilities.json") as f:
            data = json.load(f)
        return {fac["number"]: fac for fac in data.get("facilities", []) if fac.get("number")}
    except FileNotFoundError:
        return {}


def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, separators=(",", ":"))


def load_closed():
    try:
        with open(CLOSED_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_closed(numbers):
    with open(CLOSED_FILE, "w") as f:
        json.dump(sorted(numbers), f, indent=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--county", nargs="+", help="Limit to specific counties (can specify multiple)")
    parser.add_argument("--resume", action="store_true", help="Continue an interrupted run using the checkpoint file")
    parser.add_argument("--full", action="store_true", help="Re-fetch all facilities, ignoring existing data/facilities.json")
    args = parser.parse_args()

    os.makedirs("data", exist_ok=True)

    print("Fetching childcare facility types…")
    childcare_types = get_childcare_types()
    print(f"  {len(childcare_types)} types")

    print("Fetching counties…")
    counties = get_counties()
    if args.county:
        counties = args.county
    print(f"  {len(counties)} counties to search")

    print("\nPhase 1: Discovering facilities…")
    all_facilities = discover_facilities(childcare_types, counties)

    print("\nPhase 2: Fetching facility details…")
    existing = load_existing()
    known_closed = load_closed()
    checkpoint = load_cache() if args.resume else {}

    output_map = {**existing, **checkpoint}

    already_fetched = (set(checkpoint) if args.full else set(existing) | set(checkpoint)) | known_closed

    to_fetch = [(n, i) for n, i in all_facilities.items() if n not in already_fetched]
    total = len(to_fetch)
    print(f"  {total} to fetch, {len(output_map)} already in data, {len(known_closed)} closed (skipped)")

    for i, (fnum, info) in enumerate(to_fetch):
        if i % 200 == 0 and i > 0:
            pct = i * 100 // total
            print(f"  {i}/{total} ({pct}%)…")
            save_cache(checkpoint)

        detail = get_detail(fnum)
        if detail:
            result = process(info["basic"], info["type"], detail)
            if (result.get("number") or "").lower() == "facility number not found":
                continue
            output_map[fnum] = result
            checkpoint[fnum] = result
        time.sleep(RATE_LIMIT)

    print(f"  Fetched {len(checkpoint)} facilities")

    active_map = {}
    newly_closed = set()
    for num, fac in output_map.items():
        if is_closed(fac.get("status", "")):
            newly_closed.add(num)
        else:
            active_map[num] = fac
    if not active_map and existing:
        raise RuntimeError("active_map is empty but existing data was non-empty — aborting to avoid data loss")
    all_closed = known_closed | newly_closed
    save_closed(all_closed)

    print(f"  {len(newly_closed)} closed facilities excluded ({len(all_closed)} total known closed)")

    processed = sorted(
        active_map.values(),
        key=lambda x: (x.get("most_recent_activity") or "0000-00-00"),
        reverse=True,
    )

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_facilities": len(processed),
        "facilities": processed,
    }

    with open("data/facilities.json", "w") as f:
        json.dump(output, f, indent=1)

    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    with_a = sum(1 for f in processed if f["type_a_violations"] > 0)
    with_b = sum(1 for f in processed if f["type_b_violations"] > 0)
    with_c = sum(1 for f in processed if f["total_complaints"] > 0)
    print(f"\nSaved {len(processed)} facilities → data/facilities.json")
    print(f"  Type A violations: {with_a} facilities")
    print(f"  Type B violations: {with_b} facilities")
    print(f"  With complaints:   {with_c} facilities")


if __name__ == "__main__":
    main()
