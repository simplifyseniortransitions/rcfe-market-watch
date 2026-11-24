# California RCFE Weekly Movers — Marblism integration

**Status: not sent. Send only after Dale approves the Marblism integration.**

The Weekly Movers frame shows the latest **approved** California RCFE Weekly Movers report. Every number comes
from the RCFE Deal Room Market Watch project. Marblism only places the frame and listens for its messages.

## Embed URL
`https://simplifyseniortransitions.github.io/rcfe-market-watch/weekly-movers.html`

## Recommended placement on rcfedealroom.com/market-watch
1. Latest RCFE Deal Room News
2. California RCFE Market Map
3. **California RCFE Weekly Movers** (this frame)
4. Explore the data behind the headlines
5. Existing Market Watch dashboard

## The frame
```html
<section id="weekly-movers-section" aria-label="California RCFE Weekly Movers">
  <iframe id="weekly-movers-frame"
    src="https://simplifyseniortransitions.github.io/rcfe-market-watch/weekly-movers.html"
    title="California RCFE Weekly Movers" loading="lazy" scrolling="no"
    style="width:100%;border:0;display:block;height:900px;min-height:420px"></iframe>
</section>
```
- **Start height:** 900px (a reasonable desktop first view). The frame then reports its real height.
- **Minimum height:** 420px. That fits the loading, empty and failure messages.
- **Don't add** `sandbox` or `allow` attributes. The frame needs nothing beyond scripts and its own data.

## The listener (add as its own script; leave the existing Market Watch and Market Map listeners exactly as they are)
```html
<script>
  window.addEventListener("message", function (e) {
    if (e.origin !== "https://simplifyseniortransitions.github.io") return;
    var d = e.data || {};
    if (d.type === "rcfe-weekly-movers-height") {
      var h = Math.max(420, Math.min(4000, Number(d.height) || 0));
      document.getElementById("weekly-movers-frame").style.height = h + "px";
    } else if (d.type === "rcfe-analytics" && d.event === "rcfe_weekly_movers") {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({ event: "rcfe_weekly_movers", movers_action: String(d.action || "").slice(0, 40),
                              movers_label: String(d.label || "").slice(0, 40) });
    }
  });
</script>
```
- **Allowed message origin:** `https://simplifyseniortransitions.github.io` only.
- **Message namespace:** `rcfe-weekly-movers-height` for the height, and `rcfe-analytics` with
  `event: "rcfe_weekly_movers"` for analytics. These names are separate from Market Watch (`rcfe-height`) and the
  Market Map (`rcfe-map-height`, `rcfe-map-ready`, `rcfe-map-context`, `rcfe_map_preview`). The early-access form
  sends no messages of its own.
- The frame only posts to rcfedealroom.com, www.rcfedealroom.com and rcfe-deal-room.marblism.me. It never posts
  to `*`.

## How it behaves
- **Loading:** "Loading the latest approved Weekly Movers report…"
- **No approved report yet:** "The first California RCFE Weekly Movers report is being prepared. Check back
  after the next approved weekly update."
- **Data can't load:** "Weekly Movers is temporarily unavailable. The rest of RCFE Deal Room Market Watch
  remains available." This affects this frame only. The Market Map and the Market Watch dashboard keep working.
- **Complete-report button:** shows "COMPLETE REPORT FOR FREE MEMBERS — COMING SOON", not clickable, until the
  free community report is live and approved. It is never a broken link.
- **News button:** "WATCH THE LATEST RCFE DEAL ROOM NEWS" appears only when Dale has attached an approved
  episode link to the current report.
- **Mobile:** desktop, tablet, iPhone Safari and Android Chrome widths. No sideways scrolling. Buttons are at
  least 44px tall.
- **Refresh:** a newly approved report appears within about 10 minutes (GitHub Pages caching). Visitors never
  need to clear their cache.

## Rules for Marblism
- Don't recalculate, edit or restyle the numbers. Show the frame as is.
- Don't connect to the private data repository or any RCFE Deal Room storage.
- Don't display drafts, samples or screenshots in place of the frame.
- Don't edit or hide the disclaimer.
- Don't add trackers to the frame. Analytics come only through the listener above.

## Verify the reporting period
The frame shows "Comparing CDSS files dated <date> and <date>", the source date and the approval date. To check
what is live, open
`https://simplifyseniortransitions.github.io/rcfe-market-watch/data/weekly-movers/current.json`. Its
`comparison_period` must match the frame.

## Analytics events (non-personal)
| movers_action | When |
|---|---|
| `weekly_movers_public_view` | A report is shown (once per page view) |
| `weekly_movers_period_view` | Same moment; `movers_label` is the report's source date |
| `weekly_movers_methodology_click` | Methodology opened |
| `weekly_movers_complete_report_click` | Complete-report button clicked (only once it's live) |
| `weekly_movers_news_click` | News button clicked |

**In Google Tag Manager:** add a Custom Event trigger `rcfe_weekly_movers` and a GA4 event tag that sends
`movers_action` and `movers_label`.

## Pre-publication checklist
- [ ] Dale approved the Marblism integration.
- [ ] The frame's `src` is exactly the embed URL above.
- [ ] Only the listener above was added; the other listeners are unchanged.
- [ ] Desktop: the frame grows to fit, with no inner scrollbar and no big blank gap.
- [ ] iPhone Safari and Android Chrome: no sideways scrolling; the buttons are easy to tap.
- [ ] The Market Map and the Market Watch dashboard still load and resize normally.
- [ ] The frame shows either an approved report or the "being prepared" message, never a test preview.
- [ ] The disclaimer is visible and unedited.

## Rollback
Remove the section and the listener. Nothing else on the page depends on them.
