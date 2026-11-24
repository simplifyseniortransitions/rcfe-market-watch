# RCFE Deal Room early-access list

The "Join the Early-Access List" form on the public Market Map preview saves sign-ups to a **private
Google Sheet**. It is an interest list only. It does not subscribe anyone to a newsletter, add anyone to
Mailchimp, send email or create a Community account.

```
Form on map.html (GitHub Pages, inside rcfedealroom.com/market-watch)
  → Cloudflare Worker  rcfe-early-access  (/submit: checks, cleans, rate-limits)
  → Google Apps Script web app, bound to the Sheet (shared secret)
  → Sheet "RCFE Deal Room - Market Tools Early Access", tab "Early Access Leads"
```

## Where the secrets live

| Value | Where it's kept | Never in |
|---|---|---|
| Apps Script web app address | Worker secret `SHEET_WEBHOOK_URL` | the browser, git, GitHub Pages, chat |
| Shared secret | Worker secret `SHEET_SECRET` and Apps Script → Script Properties `SHARED_SECRET` | the same |
| Turnstile secret (only if spam ever requires it) | Worker secret `TURNSTILE_SECRET` | the same |

The only public setting is the Worker's `/submit` address (`site/data/map-cta.json`, from the repository
variable `MAP_CTA_URL`). The Sheet keeps its "Restricted" sharing setting. Deploying the script as a web app
with "Anyone" access lets the Worker reach the script, not the Sheet, and the script refuses any request
without the shared secret.

## Protections

- **Origins:** only the Market Watch GitHub Pages origin and RCFE Deal Room's own domains.
- **Honeypot field:** a filled-in honeypot gets a normal-looking reply and nothing is saved.
- **Rate limits** (Cloudflare's free rate-limiting binding, applied per location):
  - 5 requests a minute per IP address;
  - the same email again within a minute is acknowledged without a second write.
- **Validation:**
  - required fields, an 8 KB body cap and length caps on every field;
  - email format;
  - only the listed roles and features are accepted;
  - consent must be `true`.
- **Spreadsheet safety:**
  - Values starting with `=`, `+`, `-`, `@`, a tab or a carriage return are stored as plain text (apostrophe prefix). This happens in the Worker and again in the script.
  - Control characters are removed.
- **Public replies:** always `{"ok":false}` (plus the names of fields with problems), never details. Logs hold no personal data.
- **Server-set values:**
  - The submission ID and time are made on the server.
  - Status is always "New" and Internal Notes are left empty.
  - Source page and referrer keep only scheme, host and path.
- **Duplicates:** matched by lowercase email.
  - A repeat sign-up updates Role, County, Feature Interest, Consent, Source, Referrer and UTM columns on the existing row.
  - It never changes the ID, first date, name, email, Status or Internal Notes.
  - The reply is the same as for a first sign-up, so the form never reveals who is on the list.
  - Writes run under a script lock, so two at once can't create a duplicate.

## One-time setup (after approval)

1. **Create the Sheet.** In Google Drive: New → Google Sheets. Name it
   `RCFE Deal Room - Market Tools Early Access` and leave sharing as Restricted.
2. **Add the script.**
   1. Extensions → Apps Script.
   2. Replace the contents of `Code.gs` with `apps-script/Code.gs` from this folder, then save.
3. **Add the shared secret.** Project Settings (gear) → Script Properties → Add property:
   - name `SHARED_SECRET`;
   - value: paste what Claude put on your clipboard. Don't paste it anywhere else.
4. **Run setup.**
   1. Choose `setup` in the function menu and click Run.
   2. Allow access when Google asks (it asks to manage this spreadsheet).
   3. This creates the "Early Access Leads" tab with the 17 columns, a Status drop-down and a Dashboard tab.
5. **Deploy.**
   1. Deploy → New deployment → type **Web app**.
   2. Execute as **Me**; Who has access **Anyone**.
   3. Click Deploy and copy the Web app URL.
6. **Give the URL to the Worker, not to chat.** In the Terminal tab Claude opens, run
   `npx wrangler secret put SHEET_WEBHOOK_URL` and paste the URL at its prompt.

After that, Claude deploys the Worker, sets `MAP_CTA_URL`, commits and republishes the preview.

## Reviewing leads

- Open the Sheet.
- Change **Status** as you work each lead: New, Contacted, Qualified, Not a fit or Archived.
- Add anything in **Internal Notes**.
- The **Dashboard** tab counts submissions:
  - total and New;
  - by role, county, feature interest, UTM source and status.

## Turning on Turnstile later (only if spam gets through)

1. Create a Turnstile widget in Cloudflare.
2. Set the Worker secret `TURNSTILE_SECRET`.
3. Add the widget to the form, sending its token as `turnstile`.

The Worker already verifies the token whenever the secret is set.

## Local testing (this Mac only)

- Run `npm test`, which covers the Worker, the Apps Script against a stand-in Sheet, and the form logic.
- Run `npm run build` for a production dry-run bundle.
- **End to end:**
  1. Run `npm run mock-sheet`, which serves the real Code.gs on 127.0.0.1:8790 and writes `dev/.mock-sheet.json`.
  2. Run `npm run dev`, which reads `.dev.vars` (git-ignored, local-only values).
  3. Point `site/data/map-cta.json` at `http://127.0.0.1:8787/submit` while testing.
  4. Set it back afterwards.
