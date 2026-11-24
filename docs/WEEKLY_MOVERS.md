# California RCFE Weekly Movers

A weekly, **draft-only** report of what changed between two CDSS RCFE licensing files. Every report starts as a
Draft (or Held for data review) and becomes an approved artifact only when Dale approves it on the review screen.
This project is the single source of truth: the community site and Marblism may later display approved reports,
but never recalculate them.

The data audit behind these choices is in `WEEKLY_MOVERS_AUDIT.md`.

## Data sources
- The weekly CDSS file "Residential Care Facilities for the Elderly" (CC BY), saved by the existing weekly job
  as `snapshots/YYYY-MM-DD.csv` (date = CDSS's data date in the file name). Only files that passed every
  Market Watch check are saved there; rejected files are never used.
- Processing dates come from `site/data/qa-report.json`. Retrieval happens in the same job minutes earlier and
  is not recorded separately.

## Comparison method (methodology 1.0)
- **Active record:** Facility Status LICENSED or ON PROBATION.
- **Period:** the newest saved file against the immediately preceding one. If they are not 6–8 days apart, if
  there is no earlier file, or a file looks incomplete, the report is **Held** with the reason. It never skips
  back to an older file.
- **Statewide summary:** previous/current active records and net change, newly observed, no longer active,
  previous/current recorded licensed capacity and net change, counties and cities with a change, findings held
  for review, possible renames or duplicates.
- **Movers:** for every city and county, previous and current active records and recorded capacity, the
  change, the percentage (only when the previous value is 10 or more) and the facility changes behind it.
  The 20 largest increases and decreases of each kind are kept (the public preview shows 3).
- **Facility-level changes:** newly observed, no longer active, capacity increase/decrease, name, street
  address (review only), city, county and status changes. Each keeps the Facility Number, name, city, county,
  previous and current values, first and last observed dates, source dates, verification status and flags.
- **City** = the CDSS mailing city with the reviewed typo table applied (`pipeline/data/city_aliases.csv`).
  It is not the Census place used by the Top California RCFE Markets rankings. **County** = the CDSS label,
  as on the Market Watch county table.
- Totals are what the CDSS file shows. Holding or excluding a finding removes it from the published list
  of facility changes; it does not change the totals.

## Record-matching rules
1. **High-confidence match:** same Facility Number (always 9 digits and unique in every file so far).
2. **Probable match requiring review:** a record that left the active dataset and one that arrived at the same
   standardized street address, or with the same name in the same city. Labeled "Possible rename or
   relicensing". Never merged; both stay in the counts.
3. **Unmatched:** everything else.
4. **Possible duplicate:** two or more active records sharing a standardized address, or a name within one city,
   that did not share it the week before.
- Address wording (STREET/ST, upper/lower case, punctuation) is standardized first, so it is never a change.
- Mailing-city typos in the reviewed table, extra spaces and stray commas are not changes.

## Safe terminology
Use: Newly observed in the active dataset · No longer appearing in the active dataset · Recorded licensed
capacity increased/decreased · Facility record changed · Possible rename · Possible duplicate · Requires
verification · First observed · Last observed.

Never, without separate verification: newly opened, permanently closed, sold, acquired, changed ownership,
failed, saturated market, best or worst market. The tests scan every output for these words.

## Anomaly thresholds
All in `pipeline/movers/config.py`, each with its reason.

| Check | Starting value | Holds |
|---|---|---|
| Comparison gap | not 6–8 days | whole report |
| Required columns | any missing | whole report |
| Source schema | any column added, removed or reordered | whole report |
| Source row count | change over 2% | whole report |
| Statewide net active change | over ±40 | whole report |
| Newly observed or no longer active | over 60 | whole report |
| Statewide net recorded capacity | over ±1,500 | whole report |
| Active records with blank city/county/capacity | over 5 | whole report |
| New shared addresses or names | over 5 | whole report |
| City or county label changes on matched records | over 10 | whole report |
| One county's net change | over ±15 | that county row |
| One city's net change | over ±10 | that city row |
| One facility's capacity change | 50+ beds, or 50%+ on a home of 7+ | that finding |
| Newly observed with a license older than 60 days | any | that finding |
| Newly observed, Facility Number never seen before | any | that finding |
| Returned after missing from a file | any | that finding |
| Disappeared from the file instead of turning CLOSED | any | that finding |
| Closed Date more than 30 days before the file | any | that finding |
| Possible relicensing / duplicate / city or county change at the same street | any | that finding |

After 12 weekly comparisons, the statewide, county and city limits become "4 × the median of the last
12 weeks", never below the starting value.

## Approval workflow
States: **Draft** (default) · **Held for data review** · **Approved** · **Rejected** · **Superseded**.

1. The weekly job creates a Draft or Held report in the private data repository (`movers/drafts/`).
   A retry never replaces it.
2. Dale opens the review screen on his Mac: `.venv/bin/python movers_review.py` →
   http://127.0.0.1:5083. The first time, clone the private repository with
   `gh repo clone simplifyseniortransitions/rcfe-market-watch-data private-data`.
3. Review the totals, movers (click "N records" to see the changes behind a row), facility changes, data checks,
   and outputs. Include or exclude findings, add private notes.
4. Tick the acknowledgment and click **Approve**, or **Reject**, or **Hold for data review**.
5. Approval writes the approved files once to `movers/approved/<source date>/<report id>/` and updates the archive
   index. The screen pulls before showing and pushes after each action.

Every action is appended to `movers/reviews.jsonl`. Each line records the user, date and time, report ID,
current and previous snapshot IDs, previous and new state, included and excluded/held counts, the
acknowledgment, and the note. The weekly job has no code path that approves.

## Output contract (approved artifacts)
`movers/approved/<source date>/<report id>/`:

| File | Contents |
|---|---|
| `report.json` | Versioned JSON (`schema: weekly-movers/1`). Report ID, status, current and previous source dates, processing date, approval date, source name, methodology version, statewide summary, city movers, county movers, facility changes approved for display (grouped by type), held/excluded counts, terminology, limitations, disclaimer, spoken disclaimer, links, last updated |
| `report.md` | Human-readable report |
| `news-brief.md` | News Production Brief (the 12 sections) |
| `teleprompter-draft.md` | 2–3 minute segment, marked DRAFT — REQUIRES EDITORIAL APPROVAL |
| `social-drafts.md` | LinkedIn post, Facebook/Instagram caption, five-slide carousel outline, three video hooks (all drafts) |
| `charts.json`, `cards/*.svg` | Chart data and simple navy, gold, white and turquoise cards: statewide summary, top five city movers, top five county movers, facility-count change, recorded-capacity change, newly observed, no longer active, source and disclaimer |

`movers/approved/index.json` lists every approved and superseded report (ID, status, source date, period,
methodology version, supersedes/superseded-by, path) plus `current_report_id`. If methodology versions differ it
carries a visible `methodology_note` warning. Private notes, street addresses, administrator names and phone
numbers never appear in any approved file.

## Publication (approved reports only)
Approving a report on the review screen publishes it in one step. Nothing in the weekly job publishes.

1. **Validate** the approved report. It must be Approved, with an approval user, a time and an acknowledged
   approval line in the review log. It needs both snapshot IDs, both source dates and a methodology version.
   It must contain no held or excluded findings and no private fields, totals that reconcile, and the
   required disclaimer.
2. **Write the sanitized files** (each written once, never changed):
   - public preview `site/data/weekly-movers/reports/<id>.json`: totals and the top 3 movers only, no facility records;
   - free-community report `movers/community/reports/<id>.json` in the private repository.
3. **Check what was written:** content scan (no street addresses, emails, phone numbers, notes, paths or
   secrets) and a read-back.
4. **Move the pointers last:** `index.json`, then `current.json`, each swapped in atomically. A failure at any
   step leaves the previous files exactly as they were, and is logged in `movers/publications.jsonl`.
5. **Push** (only when the review screen runs with `--deploy`, once publication infrastructure is approved):
   commit `site/data/weekly-movers/` to main and republish GitHub Pages, the same way the weekly job does.

**Public files** (GitHub Pages, no directory listing): `data/weekly-movers/current.json` (pointer, or a valid
empty state), `index.json` (all published reports, superseded ones labeled), `reports/<id>.json`.
**Public frame:** `site/weekly-movers.html`, which reads only those files and calculates nothing.
**Sample stores** (a `.sample-only` file at the store root, e.g. `movers-sample/`) can never publish. The review
screen's "Public frame preview" shows any report as a labeled TEST PREVIEW on this Mac only.

**News episode:** on an approved report, the reviewer can add an RCFE Deal Room News episode by hand: title,
link, optional YouTube link, publication date, and an "approved" tick. It goes into `current.json` only, never
into the immutable report file. Without an approved episode, the news button is hidden.

**Cache:** GitHub Pages caches every file for 10 minutes. The frame always revalidates `current.json`
(`cache: "no-cache"`). Report files are immutable and named by report ID, so they can be cached.
**Rollback:** revert the `site/data/weekly-movers/` commit and republish gh-pages, or remove the frame on
Marblism. Market Watch and the map don't depend on these files.

## Community integration contract
See `WEEKLY_MOVERS_COMMUNITY.md`. The member report is in the private repository, not on GitHub Pages.

## Marblism integration contract
See `WEEKLY_MOVERS_MARBLISM.md`: embed URL, listener, message names, states and checklist.

## Failure behavior
- The weekly step runs last, after Publish, Members' map and Public map preview, with `continue-on-error`.
- It reads only saved snapshots and the QA report, and writes only to `private-data/movers/`. It cannot touch
  `site/`, gh-pages, `mapbuild/` or R2.
- Any error is caught. A run record is saved under `movers/runs/` (technical detail for administrators only) and
  the weekly notice gets one line: "Weekly Movers: draft created", "held for review" or "did not generate".
  A partial report is never published.

## Correction and supersession
On an approved report, click **Create corrected version**. The report is rebuilt for the same two files as a
new Draft (`-r2`), and earlier include/exclude choices carry over. When that is approved, the old report becomes
Superseded. Its approved files stay exactly as they were, with a `superseded-by.json` marker, and the archive
index links the two. Nothing is overwritten.

## Known limitations
- History starts Oct 11, 2026, so "first observed" is often "on or before Oct 11, 2026".
- CDSS sometimes drops records and adds them back, and records some closures months late.
- Possible relicensing is only detected at the same street address, or with the same name in the same city.
  A move to another city (e.g. R&A Manor, Salinas → Marina on Nov 22) is two separate records.
- City is the mailing city; about 58 CDSS county labels are known to be wrong at the source.
- Recorded licensed capacity is the license limit, not occupancy or demand.
- Thresholds rest on 6 weeks of history until 12 weeks exist.
- Text is from fixed templates (no AI service). It is plain, and still needs Dale's editorial pass.

## Future paid personalization (document only; not built)
Saved markets · follow a facility · follow a city or county · radius alerts · "What Changed Near Me?" ·
email notifications to members · paid-member exports · custom comparisons · sponsor placement · automatic social
publishing · automatic email publishing. Each would read the same approved artifacts and add its own consent,
billing and delivery rules.
