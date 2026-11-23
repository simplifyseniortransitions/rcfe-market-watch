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
