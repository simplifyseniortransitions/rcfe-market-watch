"""Human-readable files made from a Weekly Movers artifact: Markdown report, News Production Brief,
teleprompter draft, social drafts, chart data and simple SVG cards.

Everything here reads only the artifact made by report.public_artifact(), so a held or excluded finding can
never appear in a brief, script, post or chart. Text comes from fixed templates (no AI service, no cost).
"""
from datetime import date
from xml.sax.saxutils import escape

from pipeline.cities import title
from pipeline.movers import config as C

NAVY, GOLD, WHITE, TURQUOISE, INK, MUTED = "#092d4c", "#d9bd79", "#ffffff", "#1fa5a0", "#092d4c", "#5b6b78"
DRAFT_BANNER = "DRAFT — REQUIRES EDITORIAL APPROVAL"


def nice(iso):
    if not iso:
        return "unknown"
    d = date.fromisoformat(iso[:10])
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def signed(n):
    return "no change" if not n else f"{n:+,}".replace("-", "−")


def pct_text(p):
    return "" if p is None else f" ({p:+.1f}%)".replace("-", "−")


def place(name):
    return title(name) if name else name


def period(a):
    return f"{nice(a['previous_source_date'])} to {nice(a['current_source_date'])}"


def status_line(a):
    return {"approved": "Approved", "draft": "DRAFT, NOT APPROVED", "held": "HELD FOR DATA REVIEW, NOT APPROVED",
            "superseded": "Superseded", "rejected": "Rejected"}.get(a["status"], a["status"])


def all_changes(a):
    return [f for items in a["facility_changes"].values() for f in items]


# ---------------------------------------------------------------------------------------------- stories
def stories(a):
    """Up to three potential stories, from approved values only, largest first. Never a conclusion."""
    s, out = a["statewide"], []
    out.append({
        "headline": f"Active RCFE records statewide: {s['current_active']:,} ({signed(s['net_active_change'])})",
        "facts": f"{s['newly_observed']} records were newly observed in the active dataset and "
                 f"{s['no_longer_active']} no longer appear as active, from {period(a)}.",
        "why": "It is the clearest weekly read of how the state's active licensing file is moving.",
        "cannot_conclude": "It does not show how many facilities opened or closed this week, or anything about demand.",
    })
    counties = [r for k in ("count_increases", "count_decreases") for r in a["county_movers"].get(k, [])]
    if counties:
        c = sorted(counties, key=lambda r: (-abs(r["count_change"]), r["area"]))[0]
        out.append({
            "headline": f"{place(c['area'])} County: {signed(c['count_change'])} active records",
            "facts": f"{c['previous_count']:,} to {c['current_count']:,} active records{pct_text(c['count_pct'])}, "
                     f"from {c['record_count']} underlying record change(s).",
            "why": "The largest county movement this week; useful context for anyone watching that county.",
            "cannot_conclude": "One week of movement does not show a trend, saturation or an opportunity.",
        })
    caps = [f for f in all_changes(a) if f["change_type"] in ("capacity_increase", "capacity_decrease")]
    if caps:
        f = sorted(caps, key=lambda f: (-abs(f.get("change") or 0), f["id"]))[0]
        out.append({
            "headline": f"Largest recorded capacity change: {f['facility_name']}, {place(f['city'])}",
            "facts": f"Recorded licensed capacity went from {f['previous']} to {f['current']} "
                     f"({signed(f.get('change'))}).",
            "why": "A single license change can move a city's recorded capacity more than several small homes.",
            "cannot_conclude": "Recorded capacity is the license limit, not occupancy or the number of residents.",
        })
    elif a["city_movers"].get("count_increases") or a["city_movers"].get("count_decreases"):
        rows = a["city_movers"].get("count_increases", []) + a["city_movers"].get("count_decreases", [])
        c = sorted(rows, key=lambda r: (-abs(r["count_change"]), r["area"]))[0]
        out.append({
            "headline": f"{place(c['area'])}: {signed(c['count_change'])} active records",
            "facts": f"{c['previous_count']} to {c['current_count']} active records.",
            "why": "The largest city movement this week.",
            "cannot_conclude": "A small-number change in one city is not a market trend.",
        })
    return out[:3]


# ---------------------------------------------------------------------------------------------- markdown
def _area_table(rows, field, label):
    if not rows:
        return ["_None this week._", ""]
    lines = [f"| Area | County | Previous | Current | Change | Records |", "|---|---|---|---|---|---|"]
    for r in rows:
        prev, cur = (r["previous_count"], r["current_count"]) if field == "count" else \
            (r["previous_capacity"], r["current_capacity"])
        prev, cur = f"{prev:,}", f"{cur:,}"
        ch = r["count_change"] if field == "count" else r["capacity_change"]
        p = r["count_pct"] if field == "count" else r["capacity_pct"]
        pt = "small base" if p is None else f"{p:+.1f}%".replace("-", "−")
        lines.append(f"| {place(r['area'])} | {place(r['county'])} | {prev} | {cur} | {signed(ch)} ({pt}) | "
                     f"{r['record_count']} |")
    return lines + [""]


def _finding_lines(items, limit=None):
    if not items:
        return ["_None._", ""]
    lines = []
    for f in items[:limit] if limit else items:
        first = f.get("first_observed")
        first_txt = f"on or before {nice(first)}" if f.get("first_observed_is_earliest_file") else nice(first)
        detail = f.get("status_origin") or (f"{f['previous']} to {f['current']}" if f["previous"] is not None else "")
        flag = f" — Requires verification: {'; '.join(f['flags'])}" if f["flags"] else ""
        last = (f"last observed as active {nice(f['last_observed_active'])}" if f.get("last_observed_active")
                else f"last observed {nice(f.get('last_observed'))}")
        lines.append(f"- **{f['facility_name']}** ({place(f['city'])}, {place(f['county'])} County), "
                     f"#{f['facility_number']}: {detail}. First observed {first_txt}; {last}.{flag}")
    if limit and len(items) > limit:
        lines.append(f"- …and {len(items) - limit} more in the JSON report.")
    return lines + [""]


def markdown(a):
    s = a["statewide"]
    L = [f"# {C.LABEL}: {period(a)}", "",
         f"**Status:** {status_line(a)} · Report `{a['report_id']}` · Methodology {a['methodology_version']}", "",
         f"Source: {a['source_name']}. Source dates {nice(a['previous_source_date'])} (previous) and "
         f"{nice(a['current_source_date'])} (current); processed {nice(a['processing_date'])}.", "",
         "## Statewide summary", "",
         "| Measure | Previous | Current | Change |", "|---|---|---|---|",
         f"| Active records (Licensed or On Probation) | {s['previous_active']:,} | {s['current_active']:,} | "
         f"{signed(s['net_active_change'])} |",
         f"| Recorded licensed capacity | {s['previous_capacity']:,} | {s['current_capacity']:,} | "
         f"{signed(s['net_capacity_change'])} |", "",
         f"- Newly observed in the active dataset: **{s['newly_observed']}**",
         f"- No longer appearing in the active dataset: **{s['no_longer_active']}**",
         f"- Recorded capacity increased: {s['capacity_increases']} · decreased: {s['capacity_decreases']}",
         f"- Counties with a change in active records: {s['counties_with_count_change']} · cities: "
         f"{s['cities_with_count_change']}",
         f"- Records held for review: {s['findings_held_for_review']} · possible renames or duplicates: "
         f"{s['possible_renames_or_duplicates']}",
         f"- In this report: {a['counts']['included_findings']} facility-level changes shown, "
         f"{a['counts']['held_or_excluded_findings']} held, excluded or review-only.", ""]
    for kind, movers in (("County", a["county_movers"]), ("City", a["city_movers"])):
        L += [f"## {kind} movers", ""]
        if kind == "City":
            L += [f"_{a['city_note']}_", ""]
        for key, label, field in (("count_increases", "Largest increases in active records", "count"),
                                  ("count_decreases", "Largest decreases in active records", "count"),
                                  ("capacity_increases", "Largest increases in recorded capacity", "capacity"),
                                  ("capacity_decreases", "Largest decreases in recorded capacity", "capacity")):
            L += [f"### {label}", ""] + _area_table(movers.get(key, [])[:5], field, label)
    fc = a["facility_changes"]
    L += ["## Facility-level changes", ""]
    for kind in ("newly_observed", "no_longer_active", "capacity_increase", "capacity_decrease", "name_change",
                 "status_change", "city_change", "county_change", "possible_relicensing", "possible_duplicate"):
        if fc.get(kind):
            L += [f"### {C.CHANGE_LABELS[kind]} ({len(fc[kind])})", ""] + _finding_lines(fc[kind])
    L += ["## Limitations", ""] + [f"- {x}" for x in a["limitations"]] + ["", "## Disclaimer", "", a["disclaimer"], ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- brief
def news_brief(a):
    s, st = a["statewide"], stories(a)
    banner = "" if a["status"] == "approved" else f"> **{status_line(a)}.** Do not use on air until approved.\n\n"
    L = [f"# News Production Brief — {C.LABEL}", "", banner.rstrip(), "",
         "## 1. Reporting period", f"{period(a)} ({a['comparison_days']} days).", "",
         "## 2. Source and processing dates",
         f"- Source: {a['source_name']}",
         f"- Current source date: {nice(a['current_source_date'])}; previous: {nice(a['previous_source_date'])}",
         f"- Processed: {nice(a['processing_date'])}; report `{a['report_id']}`, methodology {a['methodology_version']}", "",
         "## 3. Statewide headline numbers",
         f"- Active records: {s['current_active']:,} ({signed(s['net_active_change'])} from {s['previous_active']:,})",
         f"- Newly observed in the active dataset: {s['newly_observed']}",
         f"- No longer appearing in the active dataset: {s['no_longer_active']}",
         f"- Recorded licensed capacity: {s['current_capacity']:,} ({signed(s['net_capacity_change'])})", "",
         "## 4. Top potential stories"]
    for i, x in enumerate(st, 1):
        L += [f"{i}. **{x['headline']}** — {x['facts']}"]
    L += ["", "## 5. Why each story may matter"] + [f"{i}. {x['why']}" for i, x in enumerate(st, 1)]
    L += ["", "## 6. What cannot be concluded from the data"] + \
         [f"{i}. {x['cannot_conclude']}" for i, x in enumerate(st, 1)] + [
         "- A newly observed record does not necessarily mean a facility opened; a record no longer active is not by itself a confirmed closure.",
         "- Counts do not show saturation, demand, occupancy, profitability or investment quality.", ""]
    held = a["counts"]["held_or_excluded_findings"]
    L += ["## 7. Verification or anomaly status",
          f"- Report status: {status_line(a)}.",
          f"- {held} facility-level change(s) were held, excluded or review-only and are not in this brief.",
          f"- {a['counts']['areas_held_or_excluded']} area row(s) held or excluded.", "",
          "## 8. Suggested on-screen statistics",
          f"- \"{s['current_active']:,} active RCFE records ({signed(s['net_active_change'])} this week)\"",
          f"- \"{s['newly_observed']} newly observed · {s['no_longer_active']} no longer active\"",
          f"- \"Recorded licensed capacity: {s['current_capacity']:,} ({signed(s['net_capacity_change'])})\"",
          f"- Source line: \"CDSS licensing file, {period(a)}\"", "",
          "## 9. Suggested chart or graphic",
          "- Statewide summary card, then the top five county movers as a horizontal bar chart "
          "(cards/statewide-summary.svg and cards/top-county-movers.svg). End on the source and disclaimer card.", "",
          "## 10. Mandatory spoken disclaimer", f"\"{C.SPOKEN_DISCLAIMER}\"", "",
          "## 11. Market Watch link", a["links"]["market_watch"], "",
          "## 12. Free-community link",
          a["links"]["community"] or "Not yet approved. Leave out until the free community link is approved.", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- teleprompter
def teleprompter(a):
    s, st = a["statewide"], stories(a)
    direction = "up" if s["net_active_change"] > 0 else "down" if s["net_active_change"] < 0 else "flat"
    paras = [
        f"# {DRAFT_BANNER}", "",
        f"_{C.LABEL} segment · {period(a)} · report {a['report_id']} · about 2–3 minutes_", "",
        "**[OPEN]**",
        f"Every week, California's licensing office publishes a fresh file of every RCFE in the state. "
        f"And every week, I compare it with the one before, so you don't have to. Here's what moved from "
        f"{period(a)}.", "",
        "**[STATEWIDE]**",
        f"The active dataset — that's homes listed as licensed or on probation — went from "
        f"{s['previous_active']:,} to {s['current_active']:,} records. That's {signed(s['net_active_change'])}, "
        f"so the statewide count is {direction} for the week. {s['newly_observed']} records were newly observed in "
        f"the active dataset, and {s['no_longer_active']} no longer appear as active. Recorded licensed capacity "
        f"moved {signed(s['net_capacity_change'])}, to {s['current_capacity']:,}.", "",
        "**[WHAT MOVED]**",
    ]
    for x in st[1:3]:
        paras += [f"{x['headline']}. {x['facts']} {x['why']}", ""]
    paras += [
        "**[CONTEXT]**",
        "Now, here's how to read this. Most newly observed records are pending applications that the state "
        "switched to licensed. But a record can also show up because it was missing from an earlier file. And a "
        "record that drops out of the active list may have closed weeks ago — the state sometimes records that "
        "late. So treat these as signals to look into, not conclusions.", "",
        "**[LIMITS]**",
        "Recorded capacity is the license limit, not how many residents live there. And a busy week in one "
        "county doesn't tell you whether that county has too many homes or too few. For that you need "
        "demographics, occupancy, pricing, staffing and local referral patterns.", "",
        "**[CALL TO ACTION]**",
        f"You can see the full weekly numbers on Market Watch at rcfedealroom.com/market-watch.", "",
        "**[DISCLAIMER — READ AS WRITTEN]**",
        C.SPOKEN_DISCLAIMER + " This segment is general education, not legal, financial or investment advice.", "",
    ]
    return "\n".join(paras)


# ---------------------------------------------------------------------------------------------- social
def social(a):
    s, st = a["statewide"], stories(a)
    p = period(a)
    link = a["links"]["market_watch"]
    second = st[1]["headline"] if len(st) > 1 else ""
    L = [f"# Social drafts — {C.LABEL}", "", f"**{DRAFT_BANNER}.** Not published. Use approved values only.", "",
         "## LinkedIn", "",
         f"California RCFE Weekly Movers, {p}.", "",
         f"The state's active RCFE dataset now lists {s['current_active']:,} records ({signed(s['net_active_change'])}). "
         f"{s['newly_observed']} records were newly observed in the active dataset and {s['no_longer_active']} no "
         f"longer appear as active. Recorded licensed capacity: {s['current_capacity']:,} "
         f"({signed(s['net_capacity_change'])}).", "",
         (f"Biggest county movement: {second}." if second else ""), "",
         "A newly observed record isn't necessarily a new facility, and a record leaving the active list isn't by "
         "itself a confirmed closure. Source: CDSS Community Care Licensing.", "",
         f"Full weekly numbers: {link}", "",
         "## Facebook / Instagram caption", "",
         f"This week in California RCFE licensing ({p}): {s['current_active']:,} active records, "
         f"{signed(s['net_active_change'])} for the week. {s['newly_observed']} newly observed, "
         f"{s['no_longer_active']} no longer active. Observed changes in the CDSS file, not confirmed openings or "
         f"closures. More on Market Watch: {link}", "",
         "## Five-slide carousel outline", "",
         f"1. {C.LABEL} — {p}",
         f"2. Active records: {s['current_active']:,} ({signed(s['net_active_change'])})",
         f"3. {s['newly_observed']} newly observed · {s['no_longer_active']} no longer active",
         f"4. {second or 'Recorded licensed capacity: ' + format(s['current_capacity'], ',')}",
         "5. Source: CDSS licensing file. Observed changes only, not confirmed openings or closures. "
         "See Market Watch.", "",
         "## Short-form video hooks", "",
         f"1. \"{s['newly_observed']} RCFE records showed up in California's active list this week — here's what that does and doesn't mean.\"",
         f"2. \"California's active RCFE count moved {signed(s['net_active_change'])} this week. Let's look at where.\"",
         "3. \"A record leaving the state's active list isn't always a closure. Here's how to read the weekly file.\"",
         ""]
    return "\n".join(x for x in L if x is not None)


# ---------------------------------------------------------------------------------------------- charts
def charts(a):
    s = a["statewide"]

    def bars(rows, field):
        return [{"label": place(r["area"]), "value": r[field]} for r in rows[:5]]

    cm, im = a["county_movers"], a["city_movers"]
    county = sorted(cm.get("count_increases", [])[:5] + cm.get("count_decreases", [])[:5],
                    key=lambda r: (-abs(r["count_change"]), r["area"]))[:5]
    city = sorted(im.get("count_increases", [])[:5] + im.get("count_decreases", [])[:5],
                  key=lambda r: (-abs(r["count_change"]), r["area"]))[:5]
    src = f"Source: CDSS Community Care Licensing file, {period(a)}"
    return {
        "report_id": a["report_id"], "period": period(a), "palette": {"navy": NAVY, "gold": GOLD, "white": WHITE,
                                                                     "turquoise": TURQUOISE},
        "charts": {
            "statewide-summary": {"type": "stat-card", "title": "Statewide summary", "stats": [
                {"label": "Active records", "value": s["current_active"], "change": s["net_active_change"]},
                {"label": "Recorded licensed capacity", "value": s["current_capacity"], "change": s["net_capacity_change"]},
                {"label": "Newly observed", "value": s["newly_observed"]},
                {"label": "No longer active", "value": s["no_longer_active"]}], "source": src},
            "top-city-movers": {"type": "bar", "title": "Top five city movers (active records)",
                                "bars": bars(city, "count_change"), "source": src, "note": C.CITY_NOTE},
            "top-county-movers": {"type": "bar", "title": "Top five county movers (active records)",
                                  "bars": bars(county, "count_change"), "source": src},
            "facility-count-change": {"type": "stat-card", "title": "Active records", "stats": [
                {"label": "Previous", "value": s["previous_active"]}, {"label": "Current", "value": s["current_active"]},
                {"label": "Change", "value": s["net_active_change"]}], "source": src},
            "capacity-change": {"type": "stat-card", "title": "Recorded licensed capacity", "stats": [
                {"label": "Previous", "value": s["previous_capacity"]}, {"label": "Current", "value": s["current_capacity"]},
                {"label": "Change", "value": s["net_capacity_change"]}], "source": src},
            "newly-observed": {"type": "stat-card", "title": "Newly observed in the active dataset",
                               "stats": [{"label": "Records", "value": s["newly_observed"]}], "source": src},
            "no-longer-active": {"type": "stat-card", "title": "No longer appearing in the active dataset",
                                 "stats": [{"label": "Records", "value": s["no_longer_active"]}], "source": src},
            "source-and-disclaimer": {"type": "text-card", "title": "Source and disclaimer",
                                      "text": C.SPOKEN_DISCLAIMER, "source": src},
        },
    }


def _svg(body, height=420):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}" viewBox="0 0 800 {height}" '
            f'font-family="Georgia, serif"><rect width="800" height="{height}" fill="{NAVY}"/>'
            f'<rect x="0" y="0" width="800" height="8" fill="{GOLD}"/>{body}</svg>\n')


def _num(v, change=False):
    return signed(v) if change else f"{v:,}"


def svg_cards(chart_data):
    out = {}
    for name, ch in chart_data["charts"].items():
        t = escape(ch["title"])
        foot = (f'<text x="40" y="395" fill="{GOLD}" font-size="14" font-family="Arial, sans-serif">'
                f'{escape(ch["source"])}</text>')
        head = f'<text x="40" y="60" fill="{WHITE}" font-size="30">{t}</text>'
        if ch["type"] == "stat-card":
            parts, n = [], len(ch["stats"])
            w = 720 / n
            for i, st in enumerate(ch["stats"]):
                x = 40 + i * w
                parts.append(f'<text x="{x:.0f}" y="190" fill="{WHITE}" font-size="{44 if n < 4 else 34}">'
                             f'{escape(_num(st["value"], st["label"] == "Change"))}</text>')
                parts.append(f'<text x="{x:.0f}" y="225" fill="{GOLD}" font-size="15" font-family="Arial, sans-serif">'
                             f'{escape(st["label"])}</text>')
                if "change" in st:
                    parts.append(f'<text x="{x:.0f}" y="255" fill="{TURQUOISE}" font-size="16" '
                                 f'font-family="Arial, sans-serif">{escape(signed(st["change"]))} this week</text>')
            out[name] = _svg(head + "".join(parts) + foot)
        elif ch["type"] == "bar":
            bars = ch["bars"]
            biggest = max([abs(b["value"]) for b in bars] or [1]) or 1
            parts = []
            for i, b in enumerate(bars):
                y = 100 + i * 52
                w = 360 * abs(b["value"]) / biggest
                color = TURQUOISE if b["value"] >= 0 else GOLD
                parts.append(f'<text x="40" y="{y + 24}" fill="{WHITE}" font-size="18" '
                             f'font-family="Arial, sans-serif">{escape(b["label"])}</text>')
                parts.append(f'<rect x="300" y="{y + 6}" width="{max(w, 2):.0f}" height="26" fill="{color}"/>')
                parts.append(f'<text x="{310 + w:.0f}" y="{y + 25}" fill="{WHITE}" font-size="18" '
                             f'font-family="Arial, sans-serif">{escape(signed(b["value"]))}</text>')
            if not bars:
                parts.append(f'<text x="40" y="200" fill="{WHITE}" font-size="20">No changes this week.</text>')
            out[name] = _svg(head + "".join(parts) + foot)
        else:
            words, lines, line = ch["text"].split(), [], ""
            for w in words:
                if len(line) + len(w) > 62:
                    lines.append(line)
                    line = w
                else:
                    line = f"{line} {w}".strip()
            lines.append(line)
            body = "".join(f'<text x="40" y="{130 + i * 34}" fill="{WHITE}" font-size="22">{escape(x)}</text>'
                           for i, x in enumerate(lines))
            out[name] = _svg(head + body + foot)
    return out
