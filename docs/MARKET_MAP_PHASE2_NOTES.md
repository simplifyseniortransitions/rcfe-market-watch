# Market Map, Phase 2: weekly map file (built, switched off)

Built on 2026-11-23. Counts only; the file with addresses stays private.

## What was built

- **The county each home actually sits in** (Dale's choice, 2026-11-23). The geocoder now uses the Census
  "geographies" batch, which returns the county along with each match at no extra cost. A one-time run added
  counties to the 8,995 addresses already placed. No point moved.
- **The members' map file** (`pipeline/mapdata.py`): one record per open facility, with its name (withheld
  names stay withheld), licensee, street, city, ZIP, county, the state's county label, status, beds, size,
  type, location and match quality. There's no administrator name and no phone number. Homes without a location
  are still listed, marked "pending". Manual corrections in `overrides.csv` always win.
  - Written to `mapbuild/map/v/<week>.json` plus a small pointer, `mapbuild/map/current.json`. Both are
    git-ignored and never under `site/`.
  - Nov 15 file: **3.2 MB**, which compresses to about **0.4 MB** in transfer.
- **The weekly step** in `weekly.yml`, named "Members' map file". It runs only when the repository variable
  `MAP_PUBLISH` is `on`, so it is **off**. It runs after the public site is published and can't stop that
  update. When it runs, it:
  1. Looks up only new addresses.
  2. Builds the file.
  3. Saves the cache to the private data repository.
  4. Uploads to the storage bucket, once a bucket and token exist; until then it skips the upload.
- **Weekly notice:** one extra line ("Members' map: updated" or "did not update") once the switch is on.
- **Tests:** 253 pass, covering:
  - the file's fields and dates
  - closed homes left off
  - withheld names kept
  - no administrator names or phone numbers
  - county rules
  - the pending and manual cases
  - files kept outside `site/`
  - the map step placed after the public publish, and unable to block it
  - the wording rules

## County result (Nov 15 file)

| | Facilities |
|---|---:|
| State label agrees with the location | 9,473 |
| State label is OUT-OF-STATE or blank, now given the real county | 44 |
| State label names a different California county | 56 |

Of those 56, **54 now match the usual county for their city**. That strongly suggests the location's county is the
right one. Market Watch's public county tables still use the state's labels.

## What's needed from Dale before this can go live

1. **Cloudflare R2:** turn on R2 in the Cloudflare account (Cloudflare may ask for a card, though use should stay
   in the free allowance), then I create:
   - a private bucket (test bucket first)
   - a token limited to that bucket, saved as the GitHub secret `MAP_R2_TOKEN`
   - the variables `MAP_BUCKET` and `CLOUDFLARE_ACCOUNT_ID`
2. **Pushing this to GitHub.** The code and workflow are committed on this Mac only. Pushing also saves the geocode
   cache to the private data repository. With `MAP_PUBLISH` off, the weekly job behaves exactly as before.
3. **Still open:** the optional free Geocodio fallback for the 267 homes without a location.

## Undo

Leave `MAP_PUBLISH` off (or turn it off). To remove the code entirely, revert the Phase 2 commit; the public site is
never involved.

# Phase 2b: city rankings data (built 2026-11-23, not shown anywhere yet)

## What was built

- **Official city for every home** (Dale's choice, Option B), in `pipeline/cities.py`.
  - The geocode cache now keeps each home's Census block. A one-time free re-run added it to all 8,995 placed
    addresses; no point or county changed.
  - The block is matched to its city or Census-named community using the Census 2020 block-to-place table
    (`pipeline/data/`, public domain, about 1 MB).
  - Result: 8,261 homes are in a city and 1,011 in a named community. 275 are outside both, shown as
    "<mailing city> (unincorporated)". 26 have no address.
- **Reviewed spelling list** (`pipeline/data/city_aliases.csv`, 33 entries). It holds only clear typos and
  abbreviations, such as SACRAMNETO → SACRAMENTO and S SAN FRANCISCO → SOUTH SAN FRANCISCO. Real places that only
  look similar (Coronado, Delano, Mill Valley, Santa Paula) are never merged.
- **Rankings in the members' map file:**
  - both views (facilities, licensed capacity)
  - both scopes: active licenses (the default), and active plus pending applications
  - top 20 with shared ranks for ties, and every city tied at 20th kept
  - each city's county, licensed capacity breakdown (1–6, 7–15, 16–49, 50+), capacity not listed, and share of
    its county
  - a list of measures where future ones (per 10,000 age 65+, changes) sit hidden
  - The map file grew to 4.0 MB.
- **Public top-five file:** `mapbuild/public/top-cities.json`, with city, county and totals only, plus the
  explanation text. It stays in `mapbuild/` until the public preview phase.
- **Tests:** 268 pass. New: aliases, city assignment, statuses, capacity totals and band edges, ties, county
  share, public file contents, the exact explanation text, and wording.

## What the rankings look like (Nov 15 file, active licenses)

- **Most facilities:**
  1. Los Angeles 931
  2. San Diego 195
  3. Fresno 174
  4. Mission Viejo 160
  5. San Jose 147
  - 20th place is a tie: Huntington Beach and Santa Clarita, 71 each.
- **Most licensed capacity:**
  1. Los Angeles 18,021
  2. San Diego 7,460
  3. Fresno 4,108
  4. San Jose 3,556
  5. San Francisco 3,280

**What changed because of the official-city rule:**
- **Los Angeles rises:** its neighborhoods (Northridge, Van Nuys, Granada Hills, North Hollywood…) now count toward
  it.
- **Sacramento falls from 224 to 111.** Of the 224 homes with a Sacramento mailing address, 107 are inside the City
  of Sacramento. The rest are in unincorporated communities such as Arden-Arcade (40), Vineyard (28) and Florin
  (16). Carmichael (107) now ranks on its own.
- **Fresno:** 21 homes with a Fresno mailing address sit outside the city limits.
