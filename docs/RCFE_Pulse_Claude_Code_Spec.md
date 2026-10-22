# RCFE Pulse - Claude Code Project Spec

Owner: Dale Corpus (Simplify Senior Transitions, RCFE Deal Room)
Status: Draft v2 for review (revised 2026-10-22). Do not build Phase 2 or 3 until Phase 1 passes acceptance tests.

Revision 2 adds: Market page activity and available-supply metrics (5a), a phase 2 demand metric (5b), a county probation view on the Signals page (8, 9), a "Deal Room angle" explainer for the Market page (9a), definitions for every acceptance number (12), and new open items (15). Privacy rules and content rules are unchanged.

## 1. Goal

Build a weekly market-intelligence site for California residential care facilities for the elderly (RCFEs), using the state licensing file. It should give sellers, buyers, investors, and vendors the same kind of weekly view that the existing CA RCFE Intel site provides, with these differences:

- Clearer metric definitions and published rules for every flag
- No individual administrator names or phone numbers
- Seller and buyer lead capture built into the pages
- A weekly email with county selection
- Sponsor slots kept separate from data

## 2. Source data

- Input: the statewide RCFE licensing CSV (one row per facility, about 13,300 rows, Oct 18, 2026 snapshot as the reference file).
- Likely origin: the state's public licensing dataset on data.ca.gov (Community Care Licensing Facilities). Confirm before automating:
  - Update frequency (the CDSS hub page does not state a weekly RCFE file)
  - Reuse license and attribution terms
  - Stable download URL
- Fallback: a manual drop folder. The pipeline must run from a CSV placed in `inbox/` without any download step.

## 3. Architecture

```
inbox/ (or download step)
   -> validate
   -> snapshots/YYYY-MM-DD.csv  (immutable, never overwritten)
   -> normalize
   -> compute metrics (current week)
   -> diff against previous snapshot
   -> write JSON outputs to site/data/
   -> build static site
   -> deploy (GitHub Pages or Netlify)
```

Stack suggestion: Python 3 for the pipeline (standard library csv and datetime; pandas optional). Static site generated from JSON (plain HTML and JavaScript, or a lightweight static generator). No login, no database at launch.

## 4. Pipeline steps

1. **Validate input**
   - Required columns present: Facility Type, Facility Number, Facility Name, Licensee, Facility Capacity, Facility Status, County Name, License First Date, Closed Date, Last Visit Date, Substantiated Allegations, Citation Numbers, Total Visits, Complaint Visits.
   - Row count within 10% of prior snapshot, unless a flag confirms a real change.
   - No duplicate Facility Numbers.
   - Dates parse as MM/DD/YYYY, or are blank.
   - If any check fails, do not publish. Write an error report and notify the owner.
2. **Snapshot**
   - Save the raw file as `snapshots/YYYY-MM-DD.csv`. Never overwrite. Keep the full history.
3. **Normalize**
   - Key facilities by Facility Number.
   - Keep facility type "RESIDENTIAL CARE ELDERLY" as the core set. Report "RCFE-CONTINUING CARE RETIREMENT COMMUNITY" and blank types separately, with a note.
4. **Compute metrics** (see section 5)
5. **Diff against the prior snapshot** (see section 6)
6. **Write outputs** (see section 7)
7. **Build and deploy**

## 5. Metric definitions (publish these on the site)

| Metric | Definition |
|---|---|
| Licensed facilities | Facility Status = LICENSED |
| Licensed beds | Sum of Facility Capacity for LICENSED facilities |
| Median home size | Median Facility Capacity for LICENSED facilities |
| Pending | Facility Status = PENDING |
| On probation | Facility Status = ON PROBATION |
| New licenses (7 or 90 days) | License First Date within the window |
| Closures (7 or 90 days) | Facilities that had a License First Date and either changed status to CLOSED in the diff window, or have a Closed Date within the window. Facilities with no License First Date (applications closed before a license was issued) are not counted as closures (decided 2026-10-22) |
| Ownership changes | Same Facility Number with a changed Licensee value between snapshots |
| New substantiated allegations | Increase in Substantiated Allegations between snapshots |
| Recent citations (12 months) | Count of citation numbers in the last 12 months, from the file's citation and visit fields |

Each metric shows the week-over-week change.

## 5a. Market page: activity and available supply (phase 1, by county)

Shown for each county and for California as a whole. Publish each definition on the Methodology page.

- **12-month window:** from the same calendar day one year before the snapshot date through the snapshot date, both days included. For the Oct 18, 2026 file: Oct 18, 2025 through Oct 18, 2026.
- **Licensed base:** facilities with Facility Status = LICENSED in the snapshot (end of the window).
- **Page labels:** group the metrics under two headings, **Activity** and **Available supply**. Do not use the word "opportunity" anywhere on the Market page.

**Activity (last 12 months)**

| Metric | Definition | California, Oct 18, 2026 file (all types) |
|---|---|---|
| New licenses, 12 months | Facilities whose License First Date is in the 12-month window, any current status | 1,054 |
| Closures, 12 months | Facilities with a License First Date whose Closed Date is in the 12-month window (decided 2026-10-22, open item 11) | 468 |
| Net change | New licenses, 12 months, minus closures, 12 months | +586 |
| Growth rate | New licenses, 12 months, divided by the licensed base | 12.2% |
| Churn rate | Closures, 12 months, divided by the licensed base | 5.4% |

**Available supply (as of the snapshot date)**

| Metric | Definition | California, Oct 18, 2026 file (all types) |
|---|---|---|
| Licensed homes | Facility Status = LICENSED | 8,607 |
| Pending | Facility Status = PENDING | 924 |
| On probation | Facility Status = ON PROBATION | 24 |
| Probation share | On probation divided by (LICENSED + ON PROBATION). Probation homes are still operating but are not in the LICENSED count, so they are added to the denominator | 0.28% |
| Share of licensed homes held by licensees with 3+ homes | Licensed homes whose licensee has 3 or more LICENSED homes statewide (counted across all counties, decided 2026-10-22), divided by the county's licensed homes. Licensee names are matched as in section 12 | 9.1% |
| Total licensed beds | Sum of Facility Capacity for LICENSED facilities | 212,076 |
| Median beds per home | Median Facility Capacity of LICENSED facilities | 6 |

Reference values for the largest counties (Oct 18, 2026 file, all types):

| County | Licensed | New 12m | Closures 12m | Net | Growth | Churn | Pending | On probation | Probation share | 3+ licensee share | Beds | Median beds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Los Angeles | 1,909 | 321 | 99 | +222 | 16.8% | 5.2% | 276 | 1 | 0.05% | 5.0% | 45,435 | 6 |
| Orange | 1,127 | 108 | 40 | +68 | 9.6% | 3.5% | 77 | 0 | 0.00% | 12.2% | 25,045 | 6 |
| Sacramento | 686 | 107 | 48 | +59 | 15.6% | 7.0% | 74 | 10 | 1.44% | 7.0% | 10,452 | 6 |
| San Diego | 615 | 65 | 31 | +34 | 10.6% | 5.0% | 42 | 1 | 0.16% | 10.1% | 22,171 | 6 |
| Riverside | 590 | 84 | 35 | +49 | 14.2% | 5.9% | 75 | 1 | 0.17% | 7.8% | 11,035 | 6 |

Display rules:

- Net change is not the same as the change in licensed homes. New licenses include homes that are now closed or still pending, and the licensed count also moves when homes go on or come off probation. Say this on the page next to the Activity table.
- Closures count only facilities that had a License First Date. Applications that closed before a license was issued (221 in the 12 months to Oct 18, 2026) are left out. State this on the Methodology page.
- Show a rate as "—" when the licensed base is 0. Mark rates for counties with fewer than 20 licensed homes as "small base" (17 counties in the Oct 18 file).
- All metrics follow the page's facility-type and home-size filters.

## 5b. Demand metric (phase 2, not computed yet)

**Licensed beds per 1,000 residents aged 65+, by county.**

- Formula: licensed beds in the county (section 5a) divided by the county's population aged 65 and over, times 1,000.
- Source: U.S. Census Bureau, American Community Survey 5-year estimates, **table B01001 (Sex by Age), 2020–2024 vintage** (released January 29, 2026). Geography: the 58 California counties.
- Population aged 65+ = the sum of B01001_020E through B01001_025E (men 65–66, 67–69, 70–74, 75–79, 80–84, 85+) and B01001_044E through B01001_049E (women, same age groups). Combine the margins of error as the square root of the sum of the squared margins, and publish the margin next to the rate.
- Update to the 2021–2025 vintage when the Census Bureau releases it.
- Rows with a blank county or "OUT-OF-STATE" have no Census population and are left out (none of them are LICENSED in the Oct 18 file).
- Credit line: "Population: U.S. Census Bureau, American Community Survey 2020–2024 5-year estimates, table B01001."
- Table and vintage confirmed 2026-10-22 (open item 13).

## 6. Change detection (the Feed)

Compare facility by facility, using Facility Number, between the current and prior snapshot. Record one event per change:

- New facility (new Facility Number)
- Status change (for example LICENSED to CLOSED, or PENDING to LICENSED)
- Licensee change (show the new entity name, not individuals)
- Capacity change
- New substantiated allegations (count increase)
- New complaint visits (count increase)

Each event has: date, facility name, facility number, city, county, change type, old value, new value.

Do not show administrator name changes.

## 7. Outputs

All files live in `site/data/` and include `as_of`, `source`, `generated_at`, and `snapshot_id`.

| File | Contents |
|---|---|
| `pulse.json` | Statewide totals, WoW changes, weekly activity counts |
| `feed.json` | Change events for the last 12 weeks |
| `signals.json` | Rule-based flags (section 8) for each facility |
| `owners.json` | Licensee entities with 3 or more homes: home count, bed count, counties, statuses |
| `market.json` | County table: licensed homes, beds, median size, new licenses 90d, closures 90d, WoW change |
| `facilities.json` | Searchable directory (section 9) |
| `history.json` | Weekly totals for trend charts (add after 4 weeks of snapshots) |
| `qa-report.json` | Validation results and row counts for every run |

## 8. Signals (rule-based, published)

Do not launch with a combined "distress score." Show each flag separately, with the rule written on the page:

- On probation (current status)
- Substantiated allegations, count in the last 12 months (if the file supports a date window; otherwise lifetime, labeled as lifetime)
- Closed or changed status in the last 90 days
- Complaint visits in the last 12 months above a set threshold (set with Dale)

Add a disclaimer: flags come from public records, may be out of date, and do not indicate a facility's quality or value. Add a corrections link.

County probation view (phase 2, Signals page): for each county, the number of facilities flagged under the rule "On probation (current status)" (the same rule text as above, printed on the page), and that number as a share of the county's LICENSED + ON PROBATION homes. Each county links to its list of flagged facilities. Uses the same disclaimer.

## 9. Pages (phase 1 vs later)

| Page | Phase | Contents |
|---|---|---|
| **Pulse** (home) | 1 | As-of date. Statewide totals with WoW change. Weekly activity: new licenses, closures, ownership changes, new substantiated allegations. County selector. Lead capture for the weekly email. |
| **Market** | 1 | County table with sort and filter, grouped under "Activity" and "Available supply" (section 5a). "Deal Room angle" explainer (section 9a). Trend charts after 4 weeks of snapshots. |
| **Facilities** | 1 | Search by name, city, county, status, capacity range. Columns: name, facility number, city, county, capacity, status, license first date, licensee entity, last visit, substantiated allegations count. No administrator name, phone, or full street address at launch. Facility detail page with the same fields, plus signals and feed history. |
| **Feed** | 2 | Change events for the last 12 weeks. Filter by county and event type. |
| **Signals** | 2 | Facilities with at least one signal, with the rule that triggered each. County probation view (section 8). |
| **Owners** | 2 | Licensee entities with 3 or more homes. Each entity: homes, beds, counties, statuses. |
| **Read** (weekly note) | 3 | Short human-written note each week, reviewed by Dale before publishing. Not auto-generated. |
| **Alerts** | 3 | County or facility watchlist, weekly email. |

## 9a. Market page: "Deal Room angle" explainer (phase 1)

A short box on the Market page, beside the Available supply table. Plain language. It explains what the numbers can and cannot tell a reader. It is not a valuation, a recommendation, or advice. Proposed text:

> **Deal Room angle: closed and pending homes as supply**
>
> Closed and pending licenses show supply, not a list of deals. A closed license means that operator is no longer licensed at that facility. The building may sit empty, be sold, change use, or reopen under a new operator. A pending application means someone has applied to open a home or take one over; once approved, it shows up as a new license.
>
> In California, a new owner generally applies for their own RCFE license, so a sale often appears in this data as a closure plus a new pending application rather than as an ownership change.
>
> For sellers, many recent closures and pending applications in a county can mean more homes are changing hands there. For buyers, the pending count shows how many other operators are entering the same county.
>
> These counts come only from the state licensing file. They do not show whether any property is for sale, its condition, or its price.
>
> General educational information only. Not legal, tax, licensing, valuation, or financial advice.

This paragraph uses interim wording until licensing counsel confirms the license-transfer rule (open item 15); update it once they do.

Rules for this box: no prices or price ranges, no rankings of counties as better or worse places to buy or sell, no "opportunity" wording, and no recommendations.

## 10. Lead capture and content rules

- Pulse page: "Get the weekly RCFE Pulse by county" with email and county selection. Store subscribers in the email tool Dale chooses (decide first).
- Seller and buyer CTAs: link to the Work With Us page and the Due Diligence Checklist. Do not offer an automatic price.
- Every page: "General educational information only. Not legal, tax, licensing, valuation, or financial advice."
- Sponsor slots (phase 3): clearly labeled, separate from data pages, and never placed inside metric tables.
- Do not use Home Care Multiplier branding or content.

## 11. Schedule and operations

- GitHub Actions job: runs weekly on Monday after the expected source update window, plus a manual trigger. Confirm the time with the source's actual update schedule.
- On failure: send a notification (email or GitHub issue) and keep the last good version live.
- Keep the last 52 snapshots at minimum. Keep all of them if storage allows.
- Log every run in `qa-report.json`.

## 12. Acceptance tests (Phase 1)

Using the Oct 18, 2026 snapshot, the site should show the values below.

Definitions used in this table:

- **All types:** every row in the file: RESIDENTIAL CARE ELDERLY (13,169 rows), RCFE-CONTINUING CARE RETIREMENT COMMUNITY (134 rows), and blank Facility Type (10 rows), 13,313 in all.
- **Core set:** Facility Type = RESIDENTIAL CARE ELDERLY only.
- **Windows:** "last 90 days" runs from the snapshot date minus 90 days through the snapshot date, both days included (Jul 20 through Oct 18, 2026).

Every acceptance number is measured on **all types**. The core-set value is shown for reference only.

| Acceptance number | Value | Definition | Core-set value |
|---|---:|---|---:|
| Licensed facilities | 8,607 | All types; Facility Status = LICENSED | 8,498 |
| Licensed beds | 212,076 | All types; sum of Facility Capacity for LICENSED | 177,188 |
| Median licensed home size | 6 beds | All types; median Facility Capacity for LICENSED | 6 |
| Pending facilities | 924 | All types; Facility Status = PENDING | 907 |
| Facilities on probation | 24 | All types; Facility Status = ON PROBATION | 24 |
| New licenses, last 90 days | 309 | All types; License First Date in the 90-day window, any current status | 308 |
| Closures, last 90 days | 102 | All types; Closed Date in the 90-day window, counting only facilities that have a License First Date. Changed from 136 on 2026-10-22 (open item 11): the 34 facilities with no License First Date are left out | 102 |
| Licensees with 3 or more homes | 199 | All types; 3 or more LICENSED facilities. Licensee names are matched after trimming, collapsing repeated spaces, and ignoring upper/lower case. Changed from 198 on 2026-10-22 (open item 14): "BCRG  INC. " and "BCRG INC." are the same licensee | 193 |
| Los Angeles licensed homes | 1,909 | All types; LICENSED, County Name = LOS ANGELES | 1,888 |
| Orange licensed homes | 1,127 | All types; LICENSED, County Name = ORANGE | 1,115 |
| Sacramento licensed homes | 686 | All types; LICENSED, County Name = SACRAMENTO | 685 |
| San Diego licensed homes | 615 | All types; LICENSED, County Name = SAN DIEGO | 603 |
| Riverside licensed homes | 590 | All types; LICENSED, County Name = RIVERSIDE | 586 |

Reconciliation: the 109 licensed facilities that are in "all types" but not in the core set are all continuing care retirement communities (109 LICENSED CCRCs, 34,888 beds). None of the 10 blank-type rows is licensed; all 10 are PENDING. The other differences: pending 924 − 907 = 7 CCRCs + 10 blank-type; new licenses 309 − 308 = 1 blank-type pending home.

The validation report must catch: a missing column, a duplicate facility number, a row count drop over 10%, and a bad date.

## 13. Differences from the existing CA RCFE Intel site

| Area | CA RCFE Intel | RCFE Pulse (this project) |
|---|---|---|
| Distress | Combined score | Rule-based flags, each rule published |
| Individuals | Not specified | No administrator names or phone numbers |
| AI commentary | Weekly AI read | Human-written weekly note (phase 3) |
| Lead capture | None visible | Weekly email, seller and buyer CTAs |
| Sponsors | None visible | Separate, labeled slots (phase 3) |
| Disclaimers | Advisory label on AI read | Educational disclaimer on every page |

## 14. Naming

"Pulse" is also a section name on CA RCFE Intel. Choose a distinct name before launch, for example "RCFE Deal Room Market Pulse," and confirm the name is not in use.

## 15. Open decisions for Dale

1. Confirm the data source: update frequency, reuse terms, and download URL.
2. Choose the hosting (GitHub Pages or Netlify) and the domain or subdomain.
3. Choose the email tool for the weekly pulse.
4. Set the complaint threshold for signals.
5. Decide whether to show full street addresses on facility pages.
6. Decide the product name.
7. Talk to Adler before launch. Agree on how you'll refer to each other's sites and whether he wants credit or a link.
8. Confirm how Marblism will show the pulse: embed, link, or import. This decides whether the pulse lives on the RCFE Deal Room site or on a separate domain.
9. Confirm the licensed base for growth and churn rates (5a): the LICENSED count at the end of the window (proposed). The file has no count from a year earlier until we have a year of snapshots.
10. Confirm the probation share denominator (5a, 8): LICENSED + ON PROBATION (proposed).
11. **Decided 2026-10-22:** count only closures that had a License First Date. Applications that closed before a license was issued are not closures. This applies to both closure measures (Closed Date windows and status changes to CLOSED). The 90-day closures acceptance number is now 102 (was 136); 12-month churn for California is 5.4%.
12. **Decided 2026-10-22:** the "licensees with 3+ homes" share (5a) counts each licensee's homes statewide (Los Angeles 5.0%), matching the Owners list.
13. **Decided 2026-10-22:** demand metric (5b) uses ACS table B01001, 2020–2024 5-year vintage.
14. **Decided 2026-10-22:** licensees with 3+ homes = 199 (names matched ignoring spacing and capitalization). Section 12 updated from 198.
15. **Pending counsel:** confirm with licensing counsel whether a California RCFE license transfers to a buyer. Section 9a uses interim wording ("a new owner generally applies for their own RCFE license") until then.

## 16. Build order

1. Pipeline: validate, snapshot, compute metrics, write JSON. Pass the acceptance tests.
2. Pulse, Market, and Facilities pages. Deploy.
3. Weekly automation. Run manually for four weeks before enabling the schedule.
4. Feed, Signals, and Owners (phase 2). Review the signal rules with Dale.
5. Email alerts and sponsor slots (phase 3).
