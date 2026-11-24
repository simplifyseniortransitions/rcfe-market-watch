# Public Market Map preview on rcfedealroom.com/market-watch (Phase 4)

Built locally 2026-11-23 at Dale's request, ahead of the Community launch. **Not committed, not published.**
It waits for Dale's approval.

## How it fits on the page

- The preview is its own page, `site/map.html`, shown in a **second frame** on the Marblism Market Watch page.
- The frame sits after the news section and before "Explore the data behind the headlines", which holds the
  existing Market Watch frame (Pulse, Market, Facilities and Methodology tabs).
- Market Watch itself is unchanged.
- Because the preview is a separate frame and a separate file, a problem in it can't break the Market Watch
  frame.
- The preview sends its own height message (`rcfe-map-height`), so it never resizes the Market Watch frame. The
  page's current listener resizes `market-watch-frame` on any `rcfe-height` message, which is why the preview
  must not reuse that message.

## What's public and what stays private

| Public (in `site/`, anyone can read it) | Private (never in `site/`) |
|---|---|
| `data/map-preview.json`: active facilities and licensed capacity per county (58), statewide totals, top five cities per view (city, county, totals), CDSS file date, processing date, source and explanation | Street addresses, coordinates, facility names, facility numbers, licensees: the members' map file in the private R2 bucket |
| `data/map-cta.json`: the early-access button address (or none) | The geocode cache (private data repository) |
| `assets/ca-counties.json`: Census county outlines (public domain) | The Community test site's address (never on the public page) |
| The member preview's **sample** card ("Sample Care Home, 123 Example Street"), made-up clusters and placeholder ranking bars | R2 addresses and tokens |

## Data rules

- **Active** means Licensed or On probation, all RCFE types including CCRCs. This is the same rule as the members'
  rankings.
- **County** is where the home is located. The Market tab uses the CDSS county label, so a few county counts differ
  slightly; the page says so under the map.
- **Cities** are official Census cities and named communities. Ties share a rank.

## Weekly refresh and failure isolation

- New step **"Public map preview"** in `weekly.yml`.
  - Runs after "Publish the site" and after "Members' map file", only if the map step succeeded.
  - `continue-on-error`: if it fails, last week's preview stays up, and Market Watch and the members' map are
    untouched.
- The CDSS schedule is unchanged.

## Early-access button

- **Destination:** the repository variable `MAP_CTA_URL`.
- **To change it:** set the variable, then run **Actions → Map preview settings**, which republishes only the
  button setting. The weekly run also applies it.
- **Allowed addresses:** `https://` on rcfedealroom.com, community.rcfedealroom.com, mailchi.mp, eepurl.com or
  list-manage.com.
  - Anything else, including the Community test site, is refused.
  - When no address is set, the button reads "Early-access signup opens soon".
- **Not set yet.** See the decision below.

### Existing forms on rcfedealroom.com (checked 2026-11-23)

- **Newsletter:** the home page's "Join the Newsletter" links to a Mailchimp signup page
  (`mailchi.mp/simplifyseniortransitions/…`). This is an existing, approved email platform.
- **Checklist and Contact forms:** both email Dale. The checklist form says requesters are *not* added to the
  newsletter.
- **There is no early-access or waitlist form.**

## Analytics

- rcfedealroom.com already loads **Google Tag Manager** (GTM-MTHDS5R8) and the Meta Pixel. Market Watch itself has
  no analytics, by design.
- The preview sends events to the host page only. The target is the exact rcfedealroom.com origin, never `*`.
  - Message: `{type: "rcfe-analytics", event: "rcfe_map_preview", action, label}`
  - Actions:
    - `preview_view`
    - `county_hover`
    - `county_select` (label: county name)
    - `ranking_view` (label: facilities or licensed_capacity)
    - `member_preview_view`, `member_preview_click`
    - `cta_click` (label: destination host)
    - `open_market_tab`
- The Marblism listener below pushes them into the page's existing `dataLayer`. No new analytics platform.
- **Completed early-access signups can't be tracked from here.** A Mailchimp hosted page doesn't report back. Its
  own reports (or a thank-you page with GTM) would be needed.

## Request for Marblism (send after approval)

> On the Market Watch page, add a new section between the "Latest RCFE Deal Room News" section and the "Explore the
> data behind the headlines" section. It holds one full-width frame:
>
> ```html
> <iframe id="market-map-frame" src="https://simplifyseniortransitions.github.io/rcfe-market-watch/map.html"
>   title="California RCFE Market Map preview" loading="lazy" scrolling="no"
>   style="width:100%;border:0;height:1500px;display:block"></iframe>
> ```
>
> Keep the existing Market Watch frame and its listener exactly as they are. Add this second listener:
>
> ```html
> <script>
>   window.addEventListener("message", function (e) {
>     if (e.origin !== "https://simplifyseniortransitions.github.io") return;
>     var d = e.data || {};
>     if (d.type === "rcfe-map-height") {
>       document.getElementById("market-map-frame").style.height = d.height + "px";
>     } else if (d.type === "rcfe-scroll-to-market") {
>       document.getElementById("market-watch-frame").scrollIntoView({ behavior: "smooth", block: "start" });
>     } else if (d.type === "rcfe-analytics" && d.event === "rcfe_map_preview") {
>       window.dataLayer = window.dataLayer || [];
>       window.dataLayer.push({ event: "rcfe_map_preview", map_action: String(d.action || "").slice(0, 40),
>                               map_label: String(d.label || "").slice(0, 60) });
>     }
>   });
> </script>
> ```

**In Google Tag Manager:** add a Custom Event trigger `rcfe_map_preview`, and a GA4 event tag that sends
`map_action` and `map_label`. This only works if GA4 is connected in that container; we couldn't see the container
from here.

## Rollback

- **Fastest:** ask Marblism to remove the section. Market Watch is unaffected.
- **Full:** revert the commit and republish `gh-pages`. The preview step skips harmlessly once its file is gone.
