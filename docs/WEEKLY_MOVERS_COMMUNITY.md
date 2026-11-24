# California RCFE Weekly Movers — free-community integration contract

**Status: contract only. Nothing in the community application is built or changed. Delivery needs Dale's
approval.**

The complete statewide report is for free RCFE Deal Room members. A public static file can't be limited to
members, so the member version is **not** on GitHub Pages. It is generated into the **private** data
repository, ready for the community application to ingest with its own access control.

## Where the data is
Private repository `simplifyseniortransitions/rcfe-market-watch-data`, folder `movers/community/`:

| File | Purpose |
|---|---|
| `current.json` | Pointer to the current approved report, or `"status": "empty"` |
| `index.json` | Every published report, newest first, with status (`approved` / `superseded`) and correction labels |
| `reports/<report_id>.json` | One approved report (schema `weekly-movers-community/1`). Written once, never changed |

## Authentication expectations
- Members never read these files directly, and the community never reads the private repository from the browser.
- **Recommended delivery (needs approval):** after each publication, copy `movers/community/` to a private
  storage location only the community Worker can read. For example, the private R2 bucket the members' map
  already uses, under a `weekly-movers/` prefix.
- The community Worker serves the data only to signed-in free members, server side. No keys, tokens or bucket
  addresses ever reach the browser.
- Read-only: the community never writes, approves or edits a report.

## Lookups
- **Current report:** read `current.json`. If `status` is `"published"`, load `reports/<report_id>.json`. If it
  is `"empty"`, show: "The first California RCFE Weekly Movers report is being prepared. Check back after the
  next approved weekly update."
- **History:** read `index.json` and list `reports` with `current_source_date` and `comparison_period`. Load a
  report by its `report_url` (relative to `movers/community/`).
- Identifiers match `wm-YYYY-MM-DD-rN`. Reject anything else; never build a path from user input.

## Supersession
- A corrected report gets a new ID (`-r2`, …). `current.json` points to it only after it is fully published.
- The earlier report stays in `index.json` with `"status": "superseded"` and `superseded_by`. Show "Superseded by
  a corrected version" with a link to the correction. Its file is never changed.
- The corrected report has `supersedes` set and `"label": "Corrected version"` in the index. Show that label.
- If `index.json` has a `methodology_note`, show it when comparing reports from different versions.

## Cache behavior
- Report files are immutable: cache them for as long as you like, keyed by report ID.
- `current.json` and `index.json` change on each publication: cache for 5 minutes at most.

## Error handling
- If `current.json` can't be read, show "Weekly Movers is temporarily unavailable." and keep the rest of the
  community working.
- If a report file is missing, or its `report_id` doesn't match the pointer, show the same message. Never fall
  back to a draft or a guess.

## Fields allowed for free members (exactly what the report file contains)
- **Report details:** `report_id`, `version`, `reporting_period`, `current_source_date`, `previous_source_date`,
  `processing_date`, `approval_date`, `methodology_version`, `methodology`, `supersedes`.
- **Statewide summary:** previous/current active records and net change, newly observed, no longer active,
  previous/current recorded licensed capacity and net change, counties and cities affected.
- **Movers:** `city_movers` and `county_movers`, each with up to 20 entries per list (`count_increases`,
  `count_decreases`, `capacity_increases`, `capacity_decreases`). Each entry has previous, current, change, percent
  and record count.
- **`facility_changes`:** approved records only, grouped by type: newly observed, no longer active, capacity
  increase/decrease, name, status, city and county changes, possible renames and duplicates the reviewer
  approved. Each record has the Facility Number, facility name (withheld when it is a person's name), city,
  county, previous and current values, licensed capacity, status change, License First Date, Closed Date,
  first and last observed dates, and a verification label ("Routine" or "Requires verification").
- **Also:** `counts`, `terminology`, `city_note`, `limitations`, `disclaimer`, `spoken_disclaimer`,
  `source_name`.

## Fields that must stay private (not in the files; never add them)
- Street addresses, administrator names and phone numbers.
- Review notes, the review log and the reviewer's identity.
- Held or excluded findings, and internal anomaly reasons.
- Private repository paths, credentials and tokens.

## Rules
- **The community must not recalculate movers.** Show the numbers exactly as published.
- Use the safe terminology in `terminology`. Never say opened, closed, sold, acquired, saturated, best or
  worst market.
- Always show the disclaimer with the report.
- Analytics (non-personal only): `weekly_movers_viewed`, `weekly_movers_period_changed`,
  `weekly_movers_methodology_viewed`, `weekly_movers_news_brief_copied`.
