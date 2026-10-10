# Sherlock 2.3.0 — Pre-Production Test Guide

You asked what changed and how to test it from start to finish. This guide
covers **everything since v2.2.0**, ordered so you can test in one pass on a
real device. Anything marked **[regression probe]** is something that already
broke once — check it first.

Time: ~40 minutes for the core pass, ~15 more for the full pass.
Parts 10 and 14 are new since the first draft of this guide.

---

## Part 0 — What changed since 2.2.0 (one screen)

**New behaviour you will see:**
- Paste a profile URL into the search box → the handle is extracted.
- Settings → Scan Parameters → **Username Permutations** (new toggle).
- Enrichment cards show **every** field the platform returned (previously a
  hardcoded handful). "+N more fields" means the rest are in the dialog.
- Stat cards (Found / Not Found / Errors / Total) are now **tappable** and
  none looks pre-selected.
- Country chips on the networks screen show **flag + code**.
- Sites screen header shows the database size (networks, tags).
- Email dossiers always show an avatar (Gravatar fallback).
- Profile dates read like "Apr 2019" everywhere.
- Biometric History lock has a strict mode + failure reasons.

**Fixes you should verify (things that were broken):**
- **[regression probe] Scan not starting** — a cancelled scan left the
  Search button disabled forever. Cancelling, then searching again, must work.
- **[regression probe] Biometric unlock crash on Windows** — the message
  object was built with an argument the Windows class does not accept.
- **[regression probe] Cancel leaving a scan unmarked** — ~5 of 6 cancels did
  not mark the scan cancelled.
- **RangeError storm in the log** — TabBarView placeholders churned every
  progress tick; the log should now be quiet during scans.
- Framework bumped to **flet 1.0.4** (+ ads and local-auth repackaged).

**Untouched:** ads, banners, consent flow, and ad tests — per your freeze.

---

## Part 1 — Install and first launch

1. Install the build for your platform from the release.
2. Launch. Expect: splash, then Home. **No first-run crash.**
3. Open **Settings → About**. Confirm the version reads **2.3.0 (build 13)**.
4. Check the header/logo shows correctly in both light and dark mode
   (the README now swaps the icon by colour scheme).

**Pass criteria:** app opens, version is 2.3.0/13, no crash.

---

## Part 2 — The stuck-scan regression (test this first)

This is the bug that would make the app feel broken in daily use.

1. Home, username mode. Search a common handle (e.g. `torvalds`).
2. While the scan runs, press **Cancel**.
3. Immediately press **Search** again for any name.
   **Must work.** Previously the button stayed disabled forever.
4. Repeat 3–4 times: start → cancel → start → cancel.
   Every new search must launch (progress bar moves).
5. Start a scan, then navigate Home → History → Settings → Home while it
   runs. Come back to Results. The scan must still be running, counts
   advancing.
6. Start a scan and **switch to email mode** mid-scan, then back. The scan
   must survive.

**Pass criteria:** after every cancel, a new search starts; a running scan
survives navigation and mode switches.

---

## Part 3 — Search and results (username mode)

1. Search `Nwokike`. Wait for the scan to finish.
2. **Tabs**: switch between Found / Not Found / Errors. All must respond.
3. **Stat cards**: tap each of Found / Not Found / Errors. Each must jump to
   the matching tab. **None of the four may look pre-selected** — the old
   Not-Found card looked permanently highlighted.
4. **Filter box**: type part of a site name. The list must filter and the
   counts must stay honest (stat cards keep the real totals).
5. Tap a claimed result → profile dialog opens.
6. **The big one — enrichment fields.** In the dialog, scroll to
   **All Profile Fields**. For a GitHub or similar result, confirm you see
   far more than name/bio/followers — e.g. company, blog, location,
   follower/following counts, account creation date. Compare against the
   JSON preview (the raw payload section at the bottom of the dialog):
   every key in the JSON must appear as a row.
7. Back on the results list, check a **card**: it should show a handful of
   fields labelled like "Payer Id: …" / "Locale: …" and, when there are more
   than six, a line reading "+N more fields — tap for the full profile".
8. Dates: any account-creation date must read like "Mar 15, 2010" or
   "Apr 2019", never a raw ISO string.
9. **Country flags**: results cards for sites with country tags show a flag
   emoji next to the site name.
10. Tap a link in a card → it opens. Tap the copy/share actions if present.

**Pass criteria:** tabs and stat cards work; the dialog shows every JSON key;
cards show real fields with an honest overflow hint; dates are humanized.

---

## Part 4 — Email mode

1. Switch to email mode (chip on Home, or just type/paste an email address).
2. Search a real address.
3. Tabs: Found / Not Found / Rate Limited / Unavailable — all switchable.
4. Stat cards tap through to each tab.
5. Tap a result → dialog. Check **All Profile Fields** lists everything from
   the JSON (bio, login, SSO type, timezone, contact info…).
6. **Avatar**: the dossier must always show a face — the platform avatar when
   present, a Gravatar placeholder otherwise.
7. Export an email report (CSV / HTML / PDF) and confirm it opens.

**Pass criteria:** four tabs work, all fields visible, avatar always present.

---

## Part 5 — Paste-URL search

1. Copy a profile link, e.g. `https://github.com/torvalds`.
2. Paste into the search box and press Search.
   The field should show `torvalds` and the scan must run.
3. Try `https://x.com/jack?x=1` → should extract `jack`.
4. Try `https://www.reddit.com/user/alice/` → `alice`.
5. A bare username must pass through untouched.

**Pass criteria:** handles extract correctly; scans start for them.

---

## Part 6 — Username permutations (new feature)

1. Settings → Scan Parameters → turn on **Username Permutations**.
2. Home, search `john.doe`.
3. The scan must cover `john.doe`, `john_doe`, `john-doe`, `johndoe`
   (the log/Terminal shows the expanded target count).
4. Results from all variants must merge, with the claimed row winning on a
   site both variants hit.
5. Turn the toggle off and search again — only the single handle is scanned.

**Pass criteria:** variants scan, results merge without duplicates, off means off.

---

## Part 7 — Biometric History lock

1. Settings → enable the biometric History lock (starts locked by default).
2. Home → History. It must show **locked**.
3. Tap **Unlock**.
   - On a device with no biometrics/PIN: access is granted with a log line
     (this is the intended owner rule — you are not stranded).
   - On device PIN/biometric: the OS prompt appears, then History unlocks.
   - **On Windows: this must not crash.** (It used to.)
4. Tap Unlock again and cancel the prompt → History stays locked, snack says
   "Unlock cancelled".
5. Settings → **Biometrics Only** on → unlock again. PIN fallback must be
   refused; a message explains it.
6. Background the app and return. If the relock-on-resume rule is on,
   History must be locked again.

**Pass criteria:** unlock works or degrades honestly; Windows does not crash.

---

## Part 8 — Networks screen

1. Home → Networks (sites).
2. **Country chips** must show flags: 🇬🇧 GB, 🇷🇺 RU, 🇺🇸 US, 🇵🇹 PT, 🇧🇷 BR…
   (Codes only = the old bug.)
3. The stats line shows the database size (networks + tags).
4. Search the list, toggle a category, deselect/select all — must stay smooth
   with ~5,200 rows.
5. Change the scope, run a scan, and confirm only the selected networks are
   checked.

**Pass criteria:** flags visible, counts correct, interaction smooth.

---

## Part 9 — Reports and exports

1. After a scan, export each format you support: CSV, TXT, NDJSON, JSON,
   HTML, PDF, XMind.
2. Open the HTML and PDF. Enrichment fields must appear, and dates must be
   humanized. Links must be tappable in the PDF.
3. For an email search, export the email HTML — avatar present, all fields.

**Pass criteria:** every format opens and contains the same data.

---

## Part 10 — Ads (new: revenue features added)

You approved revenue-positive ad work, so this release adds four things.
Mobile only — desktop/web renders zero-size placeholders, so skip on PC.

### 10a — Banners inside the results list (new)
On the **Results** screen, banners now appear *inside* the list, interleaved:
- A list with **more than 10** results: one banner after every 10th card.
- A list with **10 or fewer**: one banner after every 5th card.
- Capped at 15 banners per list no matter how long the list is.

1. Run a username scan. Open the **Found** tab. Count the cards between
   banners — 10.
2. Switch to **Not Found** and **Errors**. The same spacing applies (these
   tabs are often longer than Found).
3. Run an email scan. Same spacing on all four tabs.
4. Scroll a long list (100+ results). Banners should not stack and should
   stop at 8.
5. **Stability check (important):** leave the scan running and watch the
   banner slots. They must NOT flicker or reload while progress ticks —
   the ad instances are pooled and reused.

### 10b — Interstitial on export (new)
1. After a scan, export a report (PDF / CSV / HTML / any).
2. After the save succeeds, an interstitial should appear — **unless** you
   searched less than 30 seconds ago (see 10c).
3. Export twice in a row quickly: only the first should show an ad.

### 10c — Minimum 30s between interstitials (new)
1. Run a search (interstitial #1 shows).
2. Immediately export a report (no interstitial — the interval guard held).
3. Wait 30+ seconds, export again (interstitial shows).
4. You can verify the skip in the log: `interstitial skipped — Ns since the
   last one (min interval 30s)`.

### 10d — Banners no longer reload (fixed flash)
On Home / Networks / History, the banner is now the same instance across
re-renders. Previously every search or mode switch discarded the live ad and
requested a new one (visible flash, wasted request).

1. On Home, run a search, then come back. The banner should hold its
   position without a reload flash.
2. Switch Home between username/email mode repeatedly — no flash.

### Consent
Consent dialog behaviour must be unchanged (EEA/UK only).

**Report if:** banners overlap cards, spacing is wrong, a slot flickers
during a scan, or two interstitials appear back to back.

---

## Part 11 — Settings sweep

Walk every settings screen once and toggle each control:
- Recursive OSINT Search, Username Permutations, Profile Data Extraction.
- Email Intelligence switches, NSFW, exclusions, scan depth, timeout slider
  (drag and release), connections slider, retries.
- Proxy URL (paste an invalid one → must show a clear error, not crash).
- Site-DB manifest (invalid JSON → clear error), update-now, health check.
- Search keywords (see the note below).

**Pass criteria:** every control works, invalid input shows a message.

---

## Part 12 — Logs and stability

1. Run a full scan with the diagnostic terminal open (or capture the log).
2. **The log must not contain `RangeError` storms** during a scan. The old
   build produced a RangeError on nearly every progress tick.
3. Confirm lines like `Scan worker finished:` appear once per scan.

**Pass criteria:** quiet log except normal scan INFO/WARNING lines.

---

## Part 13 — Full pass (optional but recommended)

Repeat Parts 3–6 for 3 different targets: a handle that exists widely
(`torvalds`), one that exists nowhere, and one with a dot/underscore
(`john.doe`). Then an email scan for an address you own.

---

## Part 14 — Notifications (the zero-dependency set)

Flet has no OS notification API, so these are in-app equivalents.

### 14a — History badge (new)
1. Note the History tab has no badge.
2. Run a scan that finds something, then go to **Home** (or Results).
3. The **History** tab should now show a small badge with a count (1, 2, …)
   — the number of scans recorded since you last opened History.
4. Tap **History**. The badge must clear immediately.
5. Run two more scans without opening History — the badge should read 2.

### 14b — "Scan finished" on resume (new)
1. Start a scan.
2. While it runs, background the app (home button) for a few seconds.
3. Return to the app. A snackbar should appear: "Scan finished — N accounts
   for <target>" with a **View** action that jumps to Results.
4. Background and resume again — the snack must NOT repeat (it shows once).
5. If you resume while the scan is still running, no snack (nothing finished).

### 14c — History relock on resume (existing, verify)
Returning from background must lock History again (biometric lock on).

**Report if:** the badge never appears, never clears, counts wrong, or the
resume snack repeats.

---

## Known notes

- **"Search keywords" in Settings**: comma-separated terms that flag claimed
  accounts whose page mentions them (a keyword badge appears on the card).
  It does not restrict what is scanned — it only marks matches. Leave it
  empty to disable. You can verify with any scan: set a keyword that exists
  on a claimed profile and that card gains the badge.
- The app is a live-network tool: bot walls, 403s and timeouts on some sites
  are expected and shown as typed errors, not failures.
- v2.3.0 is currently published as a **pre-release**; flip it to latest only
  after your Android session passes.

## Reporting

If anything fails, note the part number, what you did, and the log lines
around it. The log now distinguishes scan-engine warnings from page errors,
which makes triage quick.
