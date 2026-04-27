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
import time
import os
import sys
import argparse
from datetime import datetime

BASE_URL = "https://www.ccld.dss.ca.gov/transparencyapi/api"
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
CAP = 250  # API result cap per query


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


def search(fac_type_id, county="", city=""):
    try:
        r = get(f"{BASE_URL}/FacilitySearch", params={
            "facType": fac_type_id,
            "facility": "", "Street": "",
            "city": city, "zip": "",
            "county": county, "facnum": ""
        })
        return r.json().get("FACILITYARRAY", [])
    except Exception as e:
        print(f"  WARN search type={fac_type_id} county={county!r} city={city!r}: {e}", file=sys.stderr)
        return []


def get_cities_in_county(county):
    """Get unique cities from a county by doing a broad search with type 850 (returns most)."""
    facs = search(850, county=county)
    cities = list({f.get("CITY", "").strip() for f in facs if f.get("CITY", "").strip()})
    return cities


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

            # If we hit the cap on a large county, drill down by city
            if at_cap and county in LARGE_COUNTIES:
                print(f"    {county}: hit cap ({CAP}), drilling by city…")
                cities = get_cities_in_county(county)
                time.sleep(RATE_LIMIT)
                for city in cities:
                    city_results = search(type_id, county=county, city=city)
                    time.sleep(RATE_LIMIT)
                    total_searches += 1
                    for f in city_results:
                        fnum = f.get("FACILITYNUMBER")
                        if fnum and fnum not in all_facilities:
                            all_facilities[fnum] = {"basic": f, "type": type_name}
                    if len(city_results) == CAP:
                        print(f"      {city}: still capped at {CAP} — some facilities may be missed")

        count = sum(1 for v in all_facilities.values() if v["type"] == type_name)
        print(f"    → {count} unique facilities so far this type")

    print(f"\n  Total unique facilities discovered: {len(all_facilities)} ({total_searches} searches)")
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
        "county": fd.get("COUNTY") or "",
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


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--county", nargs="+", help="Limit to specific counties (can specify multiple)")
    parser.add_argument("--resume", action="store_true", help="Skip already-cached facilities")
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
    cache = load_cache() if args.resume else {}
    already_cached = set(cache.keys())
    processed = list(cache.values())

    to_fetch = [(n, i) for n, i in all_facilities.items() if n not in already_cached]
    total = len(to_fetch)
    print(f"  {total} to fetch ({len(already_cached)} already cached)")

    for i, (fnum, info) in enumerate(to_fetch):
        if i % 200 == 0 and i > 0:
            pct = i * 100 // total
            print(f"  {i}/{total} ({pct}%)…")
            save_cache({f["number"]: f for f in processed})

        detail = get_detail(fnum)
        if detail:
            result = process(info["basic"], info["type"], detail)
            processed.append(result)
            cache[fnum] = result
        time.sleep(RATE_LIMIT)

    print(f"  Fetched {len(to_fetch)} details")

    # Sort: most recent activity first
    processed.sort(
        key=lambda x: (x.get("most_recent_activity") or "0000-00-00"),
        reverse=True,
    )

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_facilities": len(processed),
        "facilities": processed,
    }

    with open("data/facilities.json", "w") as f:
        json.dump(output, f, separators=(",", ":"))

    if not args.resume and os.path.exists(CACHE_FILE):
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
