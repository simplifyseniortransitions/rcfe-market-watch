# California RCFE Weekly Movers — data audit and proposed method

Audit date: 2026-11-24. Nothing has been built yet. This covers the first step of the spec: auditing the data
and proposing the method, before any code is written.

## 1. What data exists

| Item | Finding |
|---|---|
| Saved weekly snapshots | **7**: Oct 11, Oct 18, Oct 25, Nov 1, Nov 8, Nov 15, Nov 22 2026 (raw CDSS files, private data repo + this Mac) |
| Spacing | Every pair is exactly 7 days apart, so there are **6 weekly comparisons** to learn from |
| Schema | Identical header (all 70+ columns) in all 7 files |
| Rejected files | One cut-off Oct 25 download (5,989 rows) was rejected by the existing checks and is never used as a baseline |
| Rows per file | 13,301 → 13,354 (all statuses, including closed records) |

### Identifier
- **Facility Number** is the identifier. It is always 9 digits, never blank, and unique in every file. The existing
  validation already fails the whole run if a number repeats or is blank.
- A number never changed hands between facilities in the 6 weeks checked.
- In California a new licensee normally needs a new license, so a **new owner usually means a new Facility Number**.
  The old number turns CLOSED and a new number appears at the same address. The data cannot confirm this; it can
  only show "possible relicensing at the same address — requires verification".

### Stability of the fields (active records, week to week)
| Field | Changes per week (6 weeks) | Comment |
|---|---|---|
| Facility Capacity | 1–4 | Never blank for active records. Some large jumps (500→582, 176→250, 39→58) |
| Facility Name | 0–2 | Real renames seen (e.g. "Morningstar … West San Jose" → "Clearwater West San Jose") |
| Street address, raw text | 15–168 | Almost all are CDSS re-typing (upper/lower case, "DRIVE" vs "DR") |
| Street address, standardized | 3–13 | After the map's existing address standardizer. Still includes real corrections |
| City | 0–1 | "MIRA LOMA" → "Jurupa Valley"; "BAKERSFIELD," → "Bakersfield" |
| County | 0 | No county label changed in 6 weeks |
| ZIP (5-digit) | 0–2 | |
| Licensee | 1–6 | Not part of Weekly Movers (already in the Market Watch feed) |
| Facility Status | ~35–40 | The main driver of weekly movement |

### Normalization
- **County:** CDSS county names are consistent (upper case, 50 counties with active homes). One active home has a
  blank county (Vallejo). The Market Map audit already found about 58 homes whose CDSS county label is wrong
  (for example Los Angeles-area homes labeled Napa). Those labels are stable week to week, so they do not create
  false weekly movement, but they do sit in the wrong county's totals.
- **City:** the CDSS mailing city is messy: 538 spellings for active homes, with typos ("ANANHEIM", "CONORD",
  "SACRAMNETO", "REDLANDS,") and mailing names that cross county lines. The project already has a reviewed
  typo table (`pipeline/data/city_aliases.csv`, 33 entries) and, for the map rankings, an official Census-place
  city from the private geocode cache.
- **Capacity** is stored consistently as a whole number for every active record.
- **Status** is preserved in every file: LICENSED, ON PROBATION, PENDING, CLOSED.

## 2. The five dates

| Date | Where it comes from today | Reliable? |
|---|---|---|
| Source publication date | The date in the CDSS file name (`ResidentialElderCareFacility11222026.csv` → Nov 22). It is the snapshot ID | Yes |
| File retrieval date | Not stored on its own. The GitHub job downloads and processes within minutes, so it is close to the processing date. Oct 11–25 were downloaded by hand | Approximate |
| Processing date | `generated_at` of the passing run in `qa-report.json` | Yes |
| First observed | Can be worked out from the snapshots, but only back to **Oct 11 2026**. Anything already in that file shows as "first observed on or before Oct 11, 2026" | Limited |
| Last observed | Can be worked out from the snapshots | Yes |

Recommendation: no change to the download now. Weekly Movers records the source date, the processing date, and
says plainly that retrieval time is the processing run's time.

## 3. Can reliable weekly comparisons be made now?

**Yes, for statewide, county and facility-level status and capacity changes**, with the limits below.

What 6 weeks show (active = LICENSED or ON PROBATION):

| Week ending | Active | Net | Newly observed | No longer active | Net recorded capacity | Counties changed | Cities changed |
|---|---|---|---|---|---|---|---|
| Oct 18 | 8,631 | +10 | 21 | 11 | +162 | 10 | 24 |
| Oct 25 | 8,622 | −9 | 13 | 22 | +33 | 13 | 27 |
| Nov 1 | 8,635 | +13 | 24 | 11 | −160 | 15 | 27 |
| Nov 8 | 8,639 | +4 | 18 | 14 | +294 | 11 | 22 |
| Nov 15 | 8,651 | +12 | 26 | 14 | +144 | 14 | 31 |
| Nov 22 | 8,657 | +6 | 17 | 11 | −263 | 10 | 26 |

The largest single county move was 6 (Los Angeles +6, Fresno −6). The largest city move was 4 (Fresno −4).

### Where "newly observed" really comes from
- Most weeks, **every** newly observed active record was a pending application whose status changed to LICENSED,
  with a License First Date 1–9 days before the file date.
- **Nov 15 is the warning case.** Nine Facility Numbers appeared as LICENSED that were in **none** of the earlier
  files. Their License First Dates run from 1993 to 2020. They are long-licensed homes that were missing from
  CDSS's file, not new homes. Two more (Tranquil Tides 448 and 452) went from CLOSED back to LICENSED.
- One home (Signature Living, Sacramento) was missing from the Nov 8 file only and came back on Nov 15.
  A naive comparison reports it as "gone" one week and "new" the next.

### Where "no longer active" comes from
- Almost always a LICENSED record turning CLOSED. The Closed Date is usually 2–10 days before the file date,
  but sometimes months or years earlier (one was 797 days earlier): CDSS records the closure late.
- Twice in 6 weeks an active record vanished from the file entirely instead of turning CLOSED.

### Same address, old record out and new record in
Seen 3 times in 6 weeks, e.g. "Oceanside Elderly Care Home 452" closed and "Tranquil Tides Senior Care 452"
appeared at the same address. This is likely a relicensing (possibly an ownership change), and must be labeled
"Possible relicensing at the same address — requires verification".

### Limitations to state in every report
1. Only 6 weekly comparisons exist, so the "unusual change" baselines are thin until about 12 weeks of history.
2. "First observed" can't go earlier than Oct 11 2026.
3. CDSS sometimes drops records and adds them back; newly observed is not newly opened.
4. CDSS records some closures weeks or months late; no longer active is not closed this week.
5. Mailing-city spellings and about 58 county labels are wrong in the source; Weekly Movers can only report CDSS's labels or corrected labels, not verify them.
6. Recorded licensed capacity is the license limit, not occupancy or demand.

## 4. Proposed method

### Definitions (methodology version 1.0)
- **Active record:** Facility Status LICENSED or ON PROBATION (the same rule as the Top California RCFE Markets
  rankings). Pending applications and closed records are not active.
- **Comparison:** the newest valid snapshot against the immediately preceding valid snapshot. If the gap is not
  7 days (±1), or either file is missing or failed validation, the report is created as **Held for data review**
  with the reason. It never silently compares against an older file.
- **Recorded licensed capacity:** sum of Facility Capacity over active records.
- **County:** the CDSS county label, so the totals match the public Market Watch county table. The blank-county
  record shows as "County not listed".
- **City:** the CDSS mailing city, cleaned (spacing, punctuation, upper case) and passed through the existing
  reviewed typo table. It is not the Census-place city used by the rankings. The report says so, so the two
  are never mixed.
- **Percentage change** only when the previous value is 10 or more; otherwise "n/a (small base)".

### Matching
1. **High-confidence match:** same Facility Number in both files. Changes in name, standardized address, city,
   county, ZIP, capacity and status are each reported as their own finding.
2. **Probable match requiring review:** a record that is no longer active and a newly observed record at the same
   standardized address (or same name in the same city). Shown as "Possible relicensing or rename". **Never
   merged automatically**; both stay in the counts.
3. **Unmatched:** everything else.
4. **Possible duplicate:** two or more active records at the same standardized address **that wasn't shared last
   week**, or the same name in the same city. The 52 addresses that already hold several licenses (campuses,
   neighboring homes) are a known baseline and are only flagged when they change.
5. Address wording changes that standardize to the same address are ignored. Real standardized changes are
   review-only findings (street addresses stay out of public files).

### Extra checks on newly observed / no longer active
- **Reappeared record:** a Facility Number seen in an earlier file, missing last week, back this week.
- **Older license newly observed:** newly observed record whose License First Date is more than 60 days before
  the file date (the Nov 15 case).
- **Missing from file:** an active record that vanished instead of turning CLOSED.
- **Late closure date:** Closed Date more than 30 days before the file date.
All four are labeled "Requires verification" and held from the public report by default.

### Anomaly thresholds (one config file, adjustable)
Starting values are set from the 6 weeks above (about 3× the largest week seen). After 12 weeks of history the
checks switch to "more than 4 times the median weekly change of the last 12 weeks, and at least the starting
floor".

| Check | Starting value | Basis |
|---|---|---|
| Statewide net active change | more than ±40 | largest seen: 13 |
| Newly observed or no longer active | more than 60 in a week | largest seen: 26 |
| Statewide net recorded capacity | more than ±1,500 | largest seen: 294 |
| Source row count change | more than 2% (the existing check already fails at a 10% drop) | weekly change has been under 0.2% |
| One facility's capacity change | 50 or more, or 50% or more on a home of 7+ | 500→582 and 176→250 were the largest |
| One county | more than ±15 net | largest seen: 6 |
| One city | more than ±10 net | largest seen: 4 |
| Possible duplicates | more than 5 new shared addresses in a week | baseline 52, stable |
| Schema | any column added, removed or renamed | header identical so far |
| Comparison gap | not 6–8 days | always 7 so far |
| Records with blank required fields | more than 5 active | 1 (blank county) |

A statewide trip, a schema change, a short file or a wrong gap holds the **whole report**. A facility-level trip
holds only that **finding**.

### Review states and approval
Draft (default) → Held for data review / Approved / Rejected; Approved → Superseded by a corrected version.
Only an explicit action in the review screen changes the state. The weekly job can only create Drafts or Held
reports. Every decision is written to an append-only log with the fields the spec lists.

## 5. Proposed build

| Piece | Where | Notes |
|---|---|---|
| Comparison, matching, anomalies, report files | `pipeline/movers/` (new) | stdlib only, same as the rest of the pipeline |
| Draft and approved reports, review log | **Private data repo**, folder `movers/` | the public repo never holds a draft |
| Review screen | `movers_review.py` → http://127.0.0.1:5083, this Mac only | same pattern as the private map preview |
| Report outputs | versioned JSON, Markdown, News Production Brief, teleprompter draft, social drafts, chart data + simple SVG cards | written from templates, no AI service, no cost |
| Weekly job | **one new step at the end** of `weekly.yml` | see below |
| Weekly notice | one added line in `pipeline/notify.py` | "Weekly Movers: draft created / held for review / did not generate" |

### The one change to the weekly job (reported before doing it, as required)
A new final step, "Weekly Movers draft", runs **after** Publish, Members' map and Public map preview. It has
`continue-on-error`, only reads the saved snapshots, and writes only to `private-data/movers/`. It cannot change
`site/`, the gh-pages branch, the map files or R2. The download, checks, tests and publish steps are untouched.

### Not in this build
No publishing of approved reports anywhere (GitHub Pages, Community, Marblism). The integration contracts
are documented only. Nothing for paid members (saved markets, follows, radius alerts, email), sponsors,
automatic social or email posting.

## 6. One existing issue found
The public Market Watch feed already labels a new Facility Number **"New facility"** (`pipeline/feed.py`). The
Nov 15 file shows those nine long-licensed homes, plus Signature Living (back after one missing week), as new
facilities. This build won't change it (it's the
public Market Watch process), but it is worth relabeling separately to "Newly listed record".
