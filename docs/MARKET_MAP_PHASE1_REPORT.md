# Market Map, Phase 1: geocoding quality report

Run on 2026-11-23 against the CDSS file dated **Nov 15, 2026**. Only facilities that aren't closed were included
(Licensed, Pending, On probation), as approved. Geocoder: U.S. Census Geocoder (free, no account), batch files of
2,000, no errors. **Nothing was published.**

This report holds counts only. Lists with addresses are in the private, git-ignored `geocache/` folder on Dale's Mac.

## Results

| | Facilities | Share |
|---|---:|---:|
| Open facilities (Licensed, Pending, On probation) | 9,573 | 100% |
| **Placed on the map** | **9,306** | **97.2%** |
| Exact match | 8,540 | 89.2% |
| Approximate match | 766 | 8.0% |
| Not placed: no match | 220 | 2.3% |
| Not placed: two or more possible matches | 21 | 0.2% |
| Not placed: no address in the CDSS file (all Pending) | 26 | 0.3% |

These 9,573 facilities share 9,231 distinct street addresses: 359 map points hold two or more licenses.

By status:
- **Licensed:** 97.7% placed (8,428 of 8,626).
- **Pending:** 92.5% placed (853 of 922). Most misses are the 26 Pending homes with no address yet.
- **On probation:** 100% placed (25 of 25).

By size:
- **6 beds or fewer:** 97.8% placed (7,548 of 7,717).
- **7 or more beds:** 94.7% placed (1,741 of 1,839).
- **Capacity blank in the CDSS file:** 100% placed (17 of 17).

## How accurate the placements are

A random sample was checked against a second, independent geocoder (OpenStreetMap's Nominatim):

| Sample | Compared | Median distance apart | Within 300 ft | Worst |
|---|---:|---:|---:|---:|
| Exact matches | 28 of 30 | **24 ft** | 26 | 506 ft |
| Approximate matches | 6 of 15 | 58 ft | 5 | 2,121 ft |

All 9,306 points fall inside California.

## What needs attention

1. **267 facilities aren't placed.** Most (232) are ordinary-looking street addresses the Census geocoder doesn't
   know. These are usually newer streets or small typos. The plan's optional fallback, Geocodio's free 2,500 a day,
   would likely place most of them. Until then, the map lists them under "location pending."
   File: `geocache/review-unplaced-2026-11-15.csv`.
2. **The CDSS county label is wrong for some facilities (new finding).** The geocoded points match the facility's
   own street, city and ZIP, but the CDSS "County Name" says otherwise.
   - Whittier, Pasadena and San Dimas homes are labeled **Napa** County.
   - Long Beach homes are labeled **Glenn** County.
   - About a dozen Sacramento-area homes are labeled **OUT-OF-STATE**.

   58 facilities are worth checking: blank or "OUT-OF-STATE" labels, or points more than 120 miles from the rest of
   their labeled county. These homes are also counted in the wrong county in Market Watch's current county tables.
   File: `geocache/review-county-labels-2026-11-15.csv`.
3. **24 approximate matches landed on a different house number** (the geocoder snapped to the nearest known
   number on that street). They'll be labeled "approximate location".
   File: `geocache/review-approximate-house-number-2026-11-15.csv`.

## Why the weekly cost stays small

- Standardizing makes **85% of CDSS's week-to-week address rewordings** (442 of 517 across five weeks) map to the
  same cached location.
- The rest average **about 15 real address changes a week**. With about 25 new facilities a week, that's **about
  40 lookups a week** after this one-time run.

## Where things are

- **Code (uncommitted, for review):**
  - `pipeline/address.py`, `pipeline/geocode.py`
  - `tests/test_address.py`, `tests/test_geocode.py` (239 tests pass in total)
  - `pipeline/config.py` (adds the `geocache/` path)
  - `.gitignore` (keeps `geocache/` out of git)
- **Cache:** `geocache/addresses.csv` and `geocache/overrides.csv`, on Dale's Mac only. They go to the private data
  repository in Phase 2, when the weekly job starts using them. Holding off avoids changing the private repository
  while the weekly job writes to it, and lets Dale review first.
- **Undo:** delete `geocache/` and the four new files. Nothing else depends on them yet.

## Questions for Dale before Phase 2

1. **County labels: DECIDED (Dale, 2026-11-23): use the county the location falls in.** The map keeps the
   state's label alongside it and notes where they differ. See section 17 of the plan.
2. **Unplaced addresses:** set up the free Geocodio fallback (needs a free account), or keep the 267 as "location
   pending" for now?
3. **Approve committing** the Phase 1 code, then start Phase 2: the weekly job geocodes only new addresses and builds
   the members' map file for a test storage bucket, with the switch off.
