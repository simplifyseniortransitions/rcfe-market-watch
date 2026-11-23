# California RCFE Market Map: audit and proposed plan

Status: **proposal for Dale's approval (2026-11-23).** Nothing in this plan has been built, geocoded, deployed or
paid for. No code, data, weekly automation or live site was changed to write it.

Projects reviewed:

- **Market Watch** (`rcfe-market-watch/`, public repo `simplifyseniortransitions/rcfe-market-watch`, private data
  repo `rcfe-market-watch-data`), live inside rcfedealroom.com/market-watch.
- **Community** (`rcfe-community/`, private repo, branch `membership-tiers`), Astro on Cloudflare Workers (free plan)
  + Supabase, test site at rcfe-community.dale-35c.workers.dev.

Facts below were measured on the CDSS file dated Nov 15, 2026 (13,337 rows) and the six saved weeks since Oct 11.

---

## 1. How the CDSS data flows today

| Step | Where | What happens |
|---|---|---|
| Download | `pipeline/download.py`, GitHub Actions `weekly.yml` | Mondays 3:30 PM PT (retries 6 PM, Tue 1 PM). CDSS "Residential Care Facilities for the Elderly" file; rejects cut-off or tiny files; 5 tries. |
| Validate | `pipeline/validate.py` | 15 required columns, unique 9-digit Facility Number, real dates, row count not down >10%. A failure publishes nothing. |
| Store | `pipeline/snapshot.py` | Exact raw copy saved as `snapshots/YYYY-MM-DD.csv` in the **private** data repo. Never overwritten. Failed files go to `snapshots/rejected/`. |
| Clean | `pipeline/normalize.py` | Builds one record per facility. **The administrator, phone and street address columns are dropped here** (`PRIVATE_COLUMNS`), and individual names are withheld. |
| Compute | `metrics.py`, `feed.py`, `signals.py` | Totals, county table, weekly changes, signals, history. |
| Publish | `pipeline/publish.py` → `site/data/*.json` → `gh-pages` | Public JSON with **no street addresses**; a test fails if any private column appears. |

Important consequence for the map: **everything Market Watch publishes is public** (public repo, public GitHub Pages
files, even though `guard.js` asks browsers to show it only inside rcfedealroom.com). So street addresses and exact
coordinates **must never go into `site/`**. Facility-level map data needs a separate, members-only channel.

## 2. Addresses and license numbers

- **Addresses are kept, privately.** Every raw weekly file in the private repo has `Facility Address`, `Facility
  City`, `Facility State`, `Facility Zip` and `County Name`. They are not carried into any published output today.
- **Stable key:** `Facility Number` (9 digits, unique in every file, checked every week). It is the license number
  CDSS uses, and it is already the key for all week-to-week comparisons.
- **Address quality (Nov 15, 9,573 not-closed facilities):**
  - 26 have no address, city, ZIP or state; **all 26 are PENDING**.
  - 4 addresses don't start with a street number, for example "ONE THOMAS MORE WAY" or "LINCOLN & 7TH STREET".
  - 19 include a unit or suite.
  - 12 have no county.
  - 172 addresses are shared by two or more open facilities (344 facilities in all). These are usually campuses
    or neighbouring licenses at one address.
  - No PO boxes.

## 3. Latitude and longitude

**None exist.** The CDSS file has no coordinate columns, and Market Watch has never geocoded anything.

## 4. How weekly changes are found today

`feed.py` compares this week with last week by Facility Number and records new facilities, status changes, licensee
changes, capacity changes, new substantiated allegations and new complaint visits. **Address changes are not
tracked** (addresses are dropped before that step). Measured last week: 22 new facility numbers and 59 "address
changes", but **55 of the 59 were only wording** (STREET vs ST and similar), 1 was a ZIP fix and only 3 were real
moves. So a standardized address is essential to avoid needless re-geocoding.

## 5. Where to standardize and geocode

A **new private stage in the weekly job**, after a file passes the checks and its snapshot is saved, and **separate
from the public publish step**:

```
download → validate → snapshot (private) → [public metrics + publish, unchanged]
                                  ↓
                     NEW: standardize addresses → geocode only new address keys → build members' map file
                          (private: GitHub Actions + private data repo + Community storage; never site/)
```

- **Standardize** in a new `pipeline/address.py`: uppercase, single spaces, no punctuation, USPS street-type and
  direction abbreviations (STREET→ST, NORTH→N), units pulled into their own field, ZIP cut to 5 digits.
  `address_key = street | city | ZIP5`.
- **Geocode** in a new `pipeline/geocode.py`, run only for keys not already in the cache.
- **The map step can fail on its own** without stopping the public Market Watch update, with its own notice line.

## 6. Storing coordinates permanently

A **geocode cache in the private data repo** (`geocache/addresses.csv`), committed alongside each week's snapshot:

- Keyed by `address_key`, so an unchanged address is **never geocoded again**, and STREET-vs-ST rewordings match
  the same key.
- A manual corrections file (`geocache/overrides.csv`) always wins over the geocoder.
- Failed lookups are remembered with a retry date, so they aren't hammered every week.
- Expected volume: a one-time run for about 9,600 open facilities (about 12,400 if closed ones were ever included),
  then **about 20–40 new addresses a week**.

## 7. Map library, tiles and geocoder: recommendation and costs

| Piece | Recommendation | Cost | Limits / notes |
|---|---|---|---|
| Map library | **MapLibre GL JS** (open source, BSD), self-hosted on the Community site | $0 | Built-in marker clustering; easily handles ~10,000 points. No third-party script. |
| Map tiles | **Protomaps California extract (OpenStreetMap)** stored in **Cloudflare R2**, served through the Community site | $0 expected | R2 free allowance (as published by Cloudflare; confirm at setup): 10 GB storage, 1M writes and 10M reads a month, **no bandwidth fees**. A California extract should fit (to be measured). Tile requests through the Worker count toward the free plan's 100,000 requests a day, roughly 1,500–3,000 map visits a day; beyond that, Workers Paid is $5/month. Requires "© OpenStreetMap contributors" credit. |
| Geocoder (main) | **U.S. Census Geocoder** batch service | $0, no account | Up to 10,000 addresses per batch file. Locations are interpolated along the street, not rooftop. I'll confirm its terms of use before relying on it. |
| Geocoder (fallback, optional) | **Geocodio** for addresses Census can't match | $0 for 2,500 lookups a day | $1 per 1,000 after that. Results may be stored permanently. Needs a free account and an API key. |

Not recommended:
- **MapTiler free:** non-commercial use only, about 5,000 map sessions a month, and its logo is required.
- **Mapbox and Google:** account keys, per-load charges after a free allowance, their own tracking scripts, and
  Google's terms limit storing geocodes.
- **The public OpenStreetMap tile server:** its usage policy forbids this kind of use.

## 8. Sharing map data securely with the Community site

**Recommended: one private R2 bucket, written by Market Watch and read only by the Community site.**

- The weekly job uploads two files with an R2 token limited to that one bucket:
  - `map/v/YYYY-MM-DD.json`: one version per week, kept for rollback.
  - `map/current.json`: a small pointer to the version the site uses.
- The token is stored as a GitHub Actions secret.
- The Community Worker reads the bucket through a binding and serves the file **only to signed-in members**
  (existing middleware), with rate limiting.
- Market Watch stays the single source of truth; the bucket is just the delivery copy.

Rejected alternatives:
- **Giving GitHub a Supabase service key:** that key can do anything in the database.
- **Having the Community site read the private GitHub repo:** ties member traffic to GitHub tokens and limits.

## 9. Where the public preview should live

**On the existing Market page of Market Watch, as a California county map shaded by facility counts.**

- It uses the county numbers already published, so there are **no addresses, no coordinates and no pins**.
- It's drawn as a simple outline by the site's own code: no map provider, no tiles, no new outside script.
- The county outlines come from the Census Bureau's free county boundary file.
- It follows the existing size and facility-type choices.
- It ends with **"See facility locations: join free"**, linking to the Community map. Because Market Watch sits
  inside a frame, the link must open the whole page, not inside the frame.

## 10. Changes needed in the Community project

- **Access:**
  - `/map` and its data address become member pages. Signed-out visitors get the existing "join free" page with a
    map-specific message.
  - The map gets a `content_status` like resources (hidden → free → pro). It **starts hidden**, so only admins
    (including preview mode) see it until Dale switches it on.
  - Future Pro tools (examples: CSV export, saved areas, change alerts) each get their own switch, **hidden by
    default**. The existing rule applies: nothing about Pro is visible while the controls are off.
- **Security:**
  - Content Security Policy: allow MapLibre's own worker file and map images from the site itself. No outside
    hosts are needed.
- **Activity tracking:**
  - Today all tracking happens on the server with no browser script, and search text is never stored. The map
    needs a small first-party script that reports map actions to the site's own address.
  - Proposed events: `map_viewed`, `map_search` (kind only: name, city, ZIP, county or address; plus county or ZIP
    if known), `map_filter_changed` (which filters), `map_facility_viewed` (facility number), and
    `map_radius_checked` (radius used).
  - **Typed addresses are not stored.**
  - Same 24-month retention as other events. The admin engagement pages get a Map section.
- **Address search:** a typed street address is looked up through a small server route that asks the Census
  geocoder. The typed address is not saved. Name, city, ZIP and county searches run in the browser against the
  loaded map file, with no outside request.
- **Privacy and terms pages:** describe map tracking and the address lookup.
- **Hosting:** an R2 binding in `wrangler.test.jsonc` (and later `wrangler.jsonc`).
- **Launch dependency:** the Community site isn't at community.rcfedealroom.com yet. The map would launch first on
  the test site.

## 11. Risks

| Risk | What could go wrong | How the plan handles it |
|---|---|---|
| Inaccurate locations | Interpolated pins can be off by a few houses, more in rural areas; new subdivisions may not match at all. | Store match quality per facility; label approximate pins; manual overrides file; fallback geocoder; never show a pin we couldn't place (list it under "location pending" instead). |
| Wrong address at the source | CDSS typos, ZIPs that don't fit the city, the 12 blank counties. | Validation report each week; corrections only by CDSS, consistent with the site's existing rule; overrides only to fix a geocode, never to change state data. |
| Duplicates | 172 shared addresses (campuses, side-by-side licenses). | Pins keyed by Facility Number, not address. Shared addresses show as one cluster listing every license there. Counts within a radius count licenses, and say so. |
| Geocoder outage | Census down or rate-limited on a Monday. | Map step soft-fails, keeps last week's coordinates, retries with the job's retries; public Market Watch update unaffected. |
| Performance | About 10,000 points and tile traffic on a free-plan Worker (10 ms CPU limit). | Map file is roughly 300 KB compressed, streamed without processing; clustering and radius counts run in the browser; tiles streamed from R2. Measured before launch, like other Community pages. |
| Privacy | Many 6-bed homes are also someone's residence; closed homes are often now private houses; typed addresses reveal buyer or seller intent. | Members only; **closed facilities left off the map** (proposed); administrator names, phones and withheld individual names stay withheld; typed addresses never stored; public preview county-level only. |
| Scraping | A member downloads the whole list. | The data is already public at CDSS, so the risk is limited; rate limiting, a members-only route and no bulk-export button (unless later as a Pro tool). |
| Misleading conclusions | Readers treat facility counts as saturation or demand. | Fixed wording: counts are "one market factor"; tests fail if "saturated", "oversaturated", "opportunity" or "should open" appears in map pages. |

## 12. Phased plan (each phase stops for Dale's approval)

1. **Address standardizing and a one-time geocode, offline, nothing published.**
   - Build `address.py` and `geocode.py`, run the Census batch once on Dale's Mac for open facilities, and save the
     cache to the private data repo.
   - Deliver a quality report: how many matched exactly, approximately, or not at all, and why.
   - *Tests:* address standardizing cases (taken from real wording differences), reuse of the cache with no
     lookup for an unchanged address, a fake geocoder for failures and retries, and that no coordinates or street
     addresses appear in `site/`.
   - *Rollback:* delete the cache files; nothing else changed.
2. **Weekly automation for the map file** (built 2026-11-23, switched off).
   - New steps in `weekly.yml` that geocode only new addresses, build the members' map file and upload it to a
     **test** R2 bucket. They sit behind a repo switch, `MAP_PUBLISH`, that starts off.
   - *Tests:* map file shape, closed facilities excluded, withheld names kept, source date and processing date
     present, and the public update still passing when the map step fails.
   - *Rollback:* turn `MAP_PUBLISH` off; the public site is never involved.
2b. **City rankings data (proposed, section 18).**
   - Standardized market city, a reviewed alias list and city totals, written into the members' map file. The top
     five per view also go into the public data.
   - *Tests:*
     - the alias list merges known misspellings and nothing else
     - every ranked home has an active license by default
     - licensed capacity sums match the facility list
     - missing capacity is counted, not guessed
     - ties share a rank and sort the same way every run
     - the public top-five file has no addresses, no coordinates and no verdict wording
   - *Rollback:* revert the commit and rebuild; the public file goes back to its current contents.
3. **Members' map on the Community test site, hidden.**
   - `/map` with clustering, search, filters, the facility card, 1/3/5/10-mile counts, source and disclaimer, and
     tracking. Includes the **Top California RCFE Markets** panel: all 20 cities, both ranking views, city
     selection and clearing (section 18). It starts hidden, so only admins see it in preview.
   - *Tests (rankings):* selecting a city fits the map to exactly that city's homes and updates the counts,
     capacity breakdown and county share; clearing restores the statewide view; the explanation text is shown
     next to the rankings; the banned words never appear.
   - *Tests:* signed-out visitors redirected, the data address refused without a session, Pro switches hidden,
     events never store typed text, radius counts against known distances, banned wording, and security headers.
   - *Rollback:* set the map to hidden (instant), redeploy the previous version, and undo the migration with its
     rollback script.
4. **Public preview on Market Watch.**
   - County map on the Market page, with a join link that opens the Community map.
   - **Top five cities** (both views) with the same explanation text and a "See all 20 cities: join free" link.
     No map pins, no city selection beyond the list.
   - *Tests:* public data still has no addresses or coordinates, wording rules, and the map works inside the frame.
   - *Rollback:* revert the commit; `gh-pages` serves the previous version within about 10 minutes.
5. **Launch.**
   - Dale switches the map to Free in Community admin and turns `MAP_PUBLISH` on for the real bucket.
   - *Rollback:* set the map back to hidden, and point `current.json` at last week's version.

## 13. Proposed data model

**Private data repo: `geocache/addresses.csv`** (one row per standardized address)

| Column | Example / meaning |
|---|---|
| address_key | `123 MAIN ST|SACRAMENTO|95814` |
| street_std, city_std, zip5 | standardized parts |
| lat, lon | decimal degrees, 6 places |
| source | `census`, `geocodio`, `manual` |
| match_quality | `exact`, `approximate`, `zip_center`, `none` |
| matched_address | what the geocoder matched |
| first_geocoded, last_checked | dates |
| attempts, last_error, retry_after | for failures |

**Private data repo: `geocache/overrides.csv`**: `facility_number` or `address_key`, lat, lon, reason, set_by, date.

**R2: `map/v/YYYY-MM-DD.json`** (members only):

```json
{ "as_of": "2026-11-15", "processed_at": "2026-11-16T23:40:00Z",
  "source": "California Department of Social Services, Community Care Licensing Division (CC BY)",
  "geocoder": "U.S. Census Bureau Geocoder", "counts": { "facilities": 9573, "placed": 9480, "pending_location": 93 },
  "facilities": [ { "id": "157209529", "name": "…", "street": "…", "city": "…", "zip": "95814", "county": "SACRAMENTO", "county_cdss": "SACRAMENTO",
    "status": "LICENSED", "capacity": 6, "size": "small", "type": "RESIDENTIAL CARE ELDERLY",
    "lat": 38.58, "lon": -121.49, "quality": "exact" } ] }
```

**Rankings (section 18)**, added to the members' map file as `cities` and `rankings`:

```json
{ "metrics": [ { "id": "facilities", "label": "Facilities", "unit": "count", "tier": "free" },
               { "id": "licensed_capacity", "label": "Licensed capacity", "unit": "count", "tier": "free" },
               { "id": "facilities_per_10k_65plus", "tier": "hidden" },
               { "id": "licensed_capacity_per_10k_65plus", "tier": "hidden" },
               { "id": "facilities_change_1w", "tier": "hidden" }, { "id": "facilities_change_12m", "tier": "hidden" } ],
  "ranking_scope": { "statuses": ["LICENSED", "ON PROBATION"], "types": "all" },
  "cities": [ { "city_id": "06-sacramento", "name": "Sacramento", "county": "SACRAMENTO",
      "facilities": 224, "licensed_capacity": 3836, "capacity_missing": 0,
      "by_capacity_band": { "1_6": 0, "7_15": 0, "16_49": 0, "50_plus": 0 },
      "county_share": { "facilities": 0.0, "licensed_capacity": 0.0 },
      "by_status": { "LICENSED": 0, "ON PROBATION": 0, "PENDING": 0 },
      "by_type": { "core": {}, "ccrc": {} } } ],
  "rankings": { "facilities": ["06-sacramento", "…"], "licensed_capacity": ["06-san-diego", "…"] } }
```

- Each facility record gains `city_id`, so selecting a city filters markers with no text matching.
- `metrics` is a registry: a future metric is one new entry plus its values, switched on by its `tier`
  (`hidden`, `free`, `pro`) without changing the panel's code.
- Public Market Watch gets `site/data/top-cities.json`: the top five per view, with city, county, facilities and
  licensed capacity only.

**Supabase (Community), new migration**

- `map_dataset_versions`: version date, processed time, counts, file key, loaded time. Audit trail and rollback.
- Map switches: the map itself plus each future Pro tool, using the existing `content_status` pattern
  (`hidden`, `coming_soon`, `free`, `pro`, `retired`).
- `member_events` gains map event names and two optional fields, `search_kind` and `area` (county or ZIP5 only).

## 14. Wireframes

**Public preview** (Market page, Market Watch)

```
┌────────────────────────────────────────────────────────────────────┐
│ FACILITIES BY COUNTY                                               │
│ [All sizes | 6 beds or fewer | 7+]  [All RCFEs | Excluding CCRCs]  │
│ ┌──────────────────────────┐  Los Angeles   1,912 licensed homes   │
│ │   California outline,    │  Orange        1,128                  │
│ │   counties shaded by     │  San Diego       616   (hover/tap a   │
│ │   licensed homes         │  …                       county)       │
│ └──────────────────────────┘                                       │
│ Counts are one market factor, not a measure of demand or           │
│ profitability. Source: CDSS CCLD, file dated Nov 15, 2026.         │
│ [ See facility locations on the full map: join free → ]            │
└────────────────────────────────────────────────────────────────────┘
```

**Full member map** (Community, /map)

```
┌───────────────────────────┬────────────────────────────────────────┐
│ Search: [name, address,   │                                        │
│  city, ZIP or county   🔍]│        Map (clusters show counts:      │
│                           │          (124)   (37)    (8)  •  •)    │
│ Status  ☑Licensed ☑Pending│                                        │
│         ☑On probation     │      ◎ selected address, ring at       │
│ Licensed capacity [1]–[200]│        1 / 3 / 5 / 10 miles            │
│ County  [ All        ▾]   │                                        │
│ City    [           ]     │                                        │
│ ZIP     [     ]           │                                        │
├───────────────────────────┤                                        │
│ Near this address         │                                        │
│  1 mi: 3   3 mi: 18       │                                        │
│  5 mi: 41  10 mi: 132     │                                        │
│ (licenses, one factor     │                                        │
│  among many)              │                                        │
├───────────────────────────┤                                        │
│ Facility card             │                                        │
│ Name · License #157209529 │                                        │
│ 123 Main St, Sacramento   │                                        │
│ Licensed · capacity 6     │                                        │
│ Location: approximate     │                                        │
│ [View full record]        │                                        │
└───────────────────────────┴────────────────────────────────────────┘
 CDSS file dated Nov 15, 2026 · processed Nov 16, 2026 · Source: CDSS CCLD (CC BY)
 · Locations: U.S. Census Geocoder (approximate) · Map © OpenStreetMap contributors
 General educational information only. Not legal, tax, licensing, valuation, or financial advice.
```

On a phone, the side panel becomes a bottom sheet over the map.

## 15. Files that would change

**Market Watch**
- New:
  - `pipeline/address.py`, `pipeline/geocode.py`, `pipeline/mapdata.py`
  - `tests/test_address.py`, `tests/test_geocode.py`, `tests/test_mapdata.py`
  - `site/assets/county-map.js`, `site/data/ca-counties.json` (county outlines only)
  - Rankings (section 18): `pipeline/cities.py`, `pipeline/city_aliases.csv`, `tests/test_cities.py`,
    `site/data/top-cities.json` (top five only), `site/assets/top-cities.js`
- Changed:
  - `pipeline/config.py` (map settings)
  - `.github/workflows/weekly.yml` (map steps behind `MAP_PUBLISH`)
  - `site/market.html`, `site/assets/market.js`, `site/assets/style.css` (preview)
  - `tests/test_pages.py` (no coordinates or addresses in public data; wording)
  - `pipeline/notify.py` (map line in the weekly email)
  - `README.md`, and the Methodology text in `site/assets/methodology.js`
- Private data repo: new `geocache/addresses.csv`, `geocache/overrides.csv`.

**Community**
- New:
  - `src/pages/map.astro`, `src/pages/api/map-data.ts`, `src/pages/api/map-events.ts`, `src/pages/api/geocode.ts`
  - `src/lib/map.ts`, `src/scripts/map.ts`, `src/components/Map*.astro`
  - `src/components/MapRankings.astro`, `src/scripts/map-rankings.ts` (rankings panel, metric registry)
  - `public/vendor/maplibre/*` (self-hosted library)
  - `supabase/migrations/2026112x_market_map.sql` and its rollback script
  - `tests/map-*.test.ts`
- Changed:
  - `src/lib/routes.ts` (map paths and the join message)
  - `src/lib/events.ts` (map events)
  - `src/lib/security.ts` (allow MapLibre's worker file and map images from the site itself)
  - `src/lib/membership.ts` (map and Pro switches)
  - `src/pages/dashboard.astro` (map link)
  - `/admin/engagement` pages (map section)
  - `src/pages/privacy.astro`, `src/pages/terms.astro`
  - `wrangler.test.jsonc`, `wrangler.jsonc` (R2 binding)
  - `docs/` (map notes)

## 16. Questions and access needed

1. **Street addresses for members.** Market Watch's rule since Oct 21 has been "no street addresses." The map
   needs them on the members-only map. OK to show them there (never on the public site)?
2. **Which facilities appear:** Licensed, Pending and On probation, with **closed facilities left off** (they're
   often private homes now)? And include CCRCs, like the headline numbers do?
3. **Withheld names:** keep showing "Name withheld (individual)" on the map where the name matches an
   administrator?
4. **Typed address searches:** OK to send a member's typed address to the free Census geocoder for the lookup,
   without saving it, and to record only the *kind* of search plus county or ZIP?
5. **Public preview level:** county only (recommended), or ZIP-level counts as well?
6. **Future Pro ideas** to prepare as hidden switches (for example CSV export, saved areas, change alerts)?
7. **Access I'll need:**
   - Cloudflare R2 turned on in your Cloudflare account. Cloudflare may ask for a card even though use should stay
     inside the free allowance.
   - An R2 token for the weekly job, which I can create once R2 is on.
   - Optionally, a free Geocodio account for the fallback geocoder.
8. **Launch order:** the Community site is still on its test address (the DNS move isn't approved), so the map
   would launch there first. Is that acceptable?

## 17. Decisions after Phase 1

- **County on the map = the county the location falls in** (Dale, 2026-11-23). The Census geographies batch
  endpoint returns the county with each match, so it costs no extra weekly lookups; the 9,231 addresses already
  cached get it in one re-run. The map file keeps the state's label as `county_cdss`, and a facility whose two
  counties differ gets a small note ("CDSS lists this facility in Napa County"). Unplaced facilities fall back to
  the state's label. This applies to the members' map only: Market Watch's published county tables keep using
  the state's label unless Dale decides otherwise.
## 18. Top California RCFE Markets panel (added 2026-11-23, for approval)

**What it is:** a panel on the left of the map, titled **"Top California RCFE Markets."** It has two views:
**Most facilities** and **Most licensed capacity**. Each lists the top 20 cities by rank, city, county, facilities
and licensed capacity. Members see all 20 and can select a city. The public preview shows the top five only.

**Wording:** "licensed capacity" is used everywhere the number comes from the CDSS `Facility Capacity` field. That's
the number of residents the license allows, not beds filled or open. No city is called "saturated,"
"undersupplied," "good" or "bad." This text appears directly under the rankings, for members and on the public
site:

> A high facility count does not necessarily indicate market saturation. It may reflect population, demand,
> established referral networks or other local conditions. Facility concentration should be evaluated alongside
> demographics, occupancy, pricing, staffing, real estate costs and local referral patterns.

### Audit (CDSS file of Nov 15, 2026)

1. **How city names are standardized today.** Market Watch trims spaces and uppercases the CDSS `Facility City`.
   The map's address step does the same and also drops punctuation. Nothing corrects spellings.
2. **Inconsistent spellings.** Open facilities use **806 raw city spellings**. Uppercasing and fixing spaces brings
   that to **562**. What's left:
   - 3 punctuation or spacing variants: "REDLANDS," with a stray comma, "N. HOLLYWOOD" and "SUNVALLEY".
   - **About 21 likely typos or abbreviations**, each on 1–2 homes, such as "SACRAMNETO", "WESTMINISTER" and
     "CITRUS HEIGHT".
   - For 59 homes, the city in the Census match differs from the CDSS city. In most of these the Census uses the
     corrected spelling; a few are neighborhood names.
   - **Proposed handling:**
     - A small alias list that Dale reviews (`pipeline/city_aliases.csv`, e.g. SACRAMNETO → SACRAMENTO), applied
       before ranking.
     - Each week, the job lists any new rare spelling that looks like a known city, for review. Nothing is merged
       automatically.
     - The facility record keeps the CDSS spelling for display.
3. **Mailing city or actual city: DECIDED (Dale, 2026-11-23): Option B, official city or community.** CDSS lists the **mailing city**, so neighborhoods inside the
   City of Los Angeles rank as separate cities.
   - Today "Los Angeles" has 181 open homes.
   - Northridge (109), Van Nuys (107), Granada Hills (98) and Woodland Hills (45) are all inside the City of Los
     Angeles, but each is listed on its own.

   Options:
   - **Option A, mailing city as listed (simplest).** It matches what members see in addresses, under the column
     name "City (mailing address)." Los Angeles looks smaller than it is.
   - **Option B, official city or community (recommended).** Use the Census "place" each home sits in: an
     incorporated city, or an unincorporated community the Census names, such as Carmichael.
     - This needs the Census block for each address. The geocoder already returns it, but we don't save it yet,
       so it takes one more free re-run, plus the Census's free table that matches blocks to places.
     - Neighborhood names stay searchable ("Van Nuys is part of Los Angeles").
     - Homes without a location use the usual place for their mailing city.
4. **Which statuses rank by default.** The file has only four statuses: Licensed 8,626, Pending 922, On probation
   25, Closed 3,764. There is no "suspended" status today.
   - **Default ranking: Licensed + On probation.** Both are active licenses.
   - **Pending:** off by default, with an "Include pending applications" switch. These are applications, not
     operating homes.
   - **Closed:** never ranked or mapped.
   - **Any new status** CDSS adds (for example, suspended) is left out of the ranking. It raises a weekly
     validation warning until a decision is made.
5. **Is licensed capacity reliable?** Yes, for the default ranking.
   - Every Licensed and On-probation home has a numeric capacity. Only **17 Pending** homes are blank.
   - No zeros or text values.
   - The largest values (up to 1,233) are big campuses and CCRCs, as expected.
   - Total licensed capacity of open homes: 233,071.
6. **Ties and missing capacity.**
   - Tied cities share a rank ("T-14"). Within a tie, order by the other measure, then city name, so the list
     stays stable week to week.
   - If several cities tie for 20th place, all of them are shown, with a note.
   - Today: no tie at 20th place in the default views. Within the top 20 there are ties at 91 and 90 facilities.
   - A home with missing capacity counts as a facility but adds nothing to capacity. The city shows "capacity not
     listed for N homes." Capacity is never estimated.
7. **County of a city.** The county where most of the city's homes are located, following your location rule.
   - A city's share of its county = the city's facilities (or licensed capacity) ÷ the county's.
   - Both use the same statuses and type filter.

**Draft top five in the default views (mailing city, Licensed + On probation):**
- **Most facilities:** Sacramento 224, Fresno 199, San Diego 186, Los Angeles 161, Mission Viejo 160.
- **Most licensed capacity:** San Diego 6,625, Los Angeles 5,864, Fresno 4,250, Sacramento 3,836, San Jose 3,520.
- These will change under Option B (now chosen), especially Los Angeles.

### Members' panel (wireframe)

```
┌─────────────────────────────────┬──────────────────────────────────────────┐
│ TOP CALIFORNIA RCFE MARKETS     │                                          │
│ [Most facilities|Most licensed  │  Map. With a city selected: zoomed to    │
│                   capacity]     │  that city's homes, its markers in full  │
│ ☐ Include pending applications  │  colour, all others dimmed.              │
│  #  City         County Fac  Cap│                                          │
│  1  Sacramento   Sacr.  224 3,836                                          │
│  2  Fresno       Fresno 199 4,250                                          │
│  …  20 rows; selected row       │                                          │
│     highlighted                 │                                          │
│ A high facility count does not  │                                          │
│ necessarily indicate market     │                                          │
│ saturation. … (full text)       │                                          │
├─────────────────────────────────┤                                          │
│ SACRAMENTO (selected) [× Clear] │                                          │
│ 224 facilities · 3,836 licensed │                                          │
│ capacity                        │                                          │
│ Homes by licensed capacity:     │                                          │
│  1–6  ███████ n   7–15  ██ n    │                                          │
│  16–49 █ n        50+   █ n     │                                          │
│ Share of Sacramento County:     │                                          │
│  n% of facilities,              │                                          │
│  n% of licensed capacity        │                                          │
└─────────────────────────────────┴──────────────────────────────────────────┘
```

- **Clear** returns the map and the counts to the statewide view.
- The size and type filters apply to the rankings too.
- On a phone, the panel becomes a tab in the bottom sheet.

### Public preview (Market page)

```
┌──────────────────────────────────────────────────────────────┐
│ TOP CALIFORNIA RCFE MARKETS [Most facilities|Most capacity]  │
│ 1 Sacramento (Sacramento County)  224 facilities  3,836 cap. │
│ … 5 rows only                                                │
│ A high facility count does not necessarily indicate … (full) │
│ [ See all 20 cities on the map: join free → ]                │
└──────────────────────────────────────────────────────────────┘
```

### Built so later versions can add these (each starts hidden)

- **Per 10,000 residents age 65+**, for facilities and for licensed capacity.
  - Source: the Census's 5-year American Community Survey (table B01001) for each place. It's already planned for
    counties in spec 5b.
  - Small places have wide margins of error, so this needs a minimum population (for example 5,000 residents
    age 65+) and a note about the margin.
- **Changes over a week, 12 months and longer:** the weekly files already exist. City totals are saved for each
  week, the way `history.json` saves county totals, so the panel can add change columns.
- **Saved city comparisons:** a Supabase table (member, cities, date) behind a Pro switch.
- **Downloadable market reports:** generated on the server from the same city data, with the explanation text and
  source line on every page, behind a Pro switch.

### Testing plan additions

- **City names:**
  - aliases merge only reviewed spellings
  - a neighborhood is never merged into a city by guesswork
  - under Option B, every placed home gets exactly one place
- **Which homes are ranked:**
  - closed homes are never counted
  - pending homes count only when the switch is on
  - unknown statuses are left out and raise a warning
- **Licensed capacity:**
  - city totals equal the sum of their homes
  - blank capacity is counted as missing, never as zero, in the breakdown
  - homes at 6/7, 15/16 and 49/50 land in the right group
- **Ties:** shared ranks, a stable order, and every tie at the cutoff shown.
- **Selecting a city:**
  - the map zooms to exactly that city's homes
  - the counts, the breakdown and the county share match the data
  - Clear restores the statewide view
- **Access:**
  - the public file holds only the top five, with no addresses or coordinates
  - members see 20
  - hidden measures are absent from the page until switched on
- **Wording:**
  - the explanation text appears wherever rankings show
  - "saturated," "undersupplied," "good" and "bad" never appear as verdicts in rankings text
  - "beds" is never used for licensed capacity in map or ranking text

### Questions for Dale (rankings)

1. **City definition: DECIDED (Dale, 2026-11-23): Option B, official city or community.**
2. **Default statuses: DECIDED (Dale, 2026-11-23): Licensed + On probation; Pending off by default, with a
   switch members can turn on.**
3. **"Beds" on the existing Market Watch pages: DECIDED (Dale, 2026-11-23): map and rankings only.** The new
   wording is "licensed capacity"; the existing public pages keep "Licensed beds" and "6 beds or fewer" as they are.

---

Sources consulted for limits and pricing (Nov 23, 2026):
- [Census Geocoder documentation](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html)
- [Census batch geocoder (10,000-record limit)](https://geocoding.geo.census.gov/geocoder/geographies/addressbatch?form)
- [Geocodio pricing](https://www.geocod.io/pricing)
- [Geocodio 2026 pricing update](https://www.geocod.io/updates/pricing-updates-2026)
- [Protomaps on Cloudflare](https://docs.protomaps.com/deploy/cloudflare)
- [Protomaps cost notes](https://docs.protomaps.com/deploy/cost)
- [MapTiler Cloud terms](https://www.maptiler.com/cloud/terms/)
- [MapTiler pricing](https://www.maptiler.com/cloud/pricing/)
