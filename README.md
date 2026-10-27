# RCFE Deal Room Market Watch

Weekly market site for California RCFEs, built from the CDSS licensing file.
Source: California Department of Social Services, Community Care Licensing Division (CC BY).

## Weekly run

1. Drop the new state CSV (e.g. `ResidentialElderCareFacility10252026.csv`) into `inbox/`.
2. Run `./run.sh`.

The date is read from the file name. If it isn't there: `./run.sh --file X.csv --as-of 2026-10-25`.

## What Step 1 does

- Checks the file. The run fails, and nothing is published, if any of these is true:
  - a required column is missing
  - a Facility Number is repeated or blank
  - a License First Date, Closed Date, or Last Visit Date is not a real M/D/YYYY date (blank is fine)
  - the row count drops more than 10% from the last good snapshot
- On a pass, saves an exact copy to `snapshots/YYYY-MM-DD.csv` and moves the input to `inbox/processed/`.
  Snapshots are never overwritten.
- On a fail, keeps the input in `inbox/` and saves a copy to `snapshots/rejected/`.
  A rejected file is never used as a comparison baseline.
- Logs every run in `site/data/qa-report.json`.

`--accept-row-drop` lets you approve a real drop of more than 10%. Each use is recorded in the report.

## What each passing run publishes (`site/data/`)

Each file is rebuilt from the saved snapshots on every run. Every file carries
`as_of`, `source`, `generated_at` and `snapshot_id`.

| File | Contents |
|---|---|
| `pulse.json` | Totals, week-over-week change, weekly activity, last 10 changes, signal counts, metric definitions |
| `feed.json` | One event per change between weekly snapshots, last 12 weeks |
| `signals.json` | Each published rule and the facilities it flags (no combined score) |
| `owners.json` | Licensees with 3+ licensed homes |
| `market.json` | County table and the five capacity bands |
| `facilities.json` | Searchable directory, with no administrator, phone number, or street address |
| `history.json` | Weekly totals, published once 4 snapshots exist |
| `qa-report.json` | Validation results for every run |

The headline numbers count every facility type in the file. Each number is also broken
down two more ways: excluding CCRCs (continuing care retirement communities), and by size
(6 beds or fewer, or 7+ beds). Blank-type rows (pending applications) count with the regular RCFEs.
If a licensee's name is the same person as an administrator (same name words, any order), it is shown
as withheld (Dale, 2026-10-21).
The administrator, phone number, and street address columns are never published.

Files are written to a staging folder first. If any file fails to build, the last good set stays in place.

## Weekly update (GitHub Actions)

The job `.github/workflows/weekly.yml` runs in the public repository:

1. Downloads the CDSS file. This is the "Residential Care Facilities for the Elderly" link on
   https://www.ccld.dss.ca.gov/carefacilitysearch/DownloadData.
2. Runs every check and the automated tests.
3. Saves the unchanged raw file in the private repository `rcfe-market-watch-data`, using a deploy key
   limited to that repository (secret `DATA_REPO_DEPLOY_KEY`).
4. Rebuilds `site/data` and republishes the site (branch `gh-pages`).

The download tries 5 times, 3 minutes apart. It rejects a cut-off file: one smaller than the size CDSS
announced, or one that doesn't end with a complete line.

If CDSS has not posted a new file, nothing is published. On any failure the site keeps last week's
version, and the failed file is kept in the private repository under `snapshots/rejected/`.

- **Schedule (Pacific time):** Monday 1 PM, then retries Monday 6 PM and Tuesday 1 PM. A retry does nothing
  once this week's file is published. Only the Tuesday 1 PM retry, or a manual run, opens an issue (about
  a failure, or about no new CDSS file), so a short CDSS outage stays quiet. Scheduled runs happen while
  the repository variable `WEEKLY_SCHEDULE` is `on`.
- **Run it by hand:** GitHub → Actions → Weekly update → Run workflow.

## Pages (`site/`)

Pulse (`index.html`), Market, Facilities, facility detail, and Methodology. They are plain
HTML and JavaScript, read only `site/data/*.json`, and load no third-party scripts, fonts, or trackers.
The email sign-up is a disabled placeholder until an email tool is chosen. There is no Corrections
page (Dale, 2026-10-22): the site says record errors can only be corrected by CDSS.

To preview on this Mac, run `.venv/bin/python serve.py`, then open http://127.0.0.1:5081.

## Tests

- `./run.sh test` runs every automated test.
- `./run.sh golden` compares the Oct 18, 2026 numbers with the acceptance values.
