# Audit — `src/screens/settings_screen.py` (1,811 lines)

Audited against installed deps only: **flet 1.0.4**, **user-scanner 1.5.2.3**, **phonsint 0.1.0** (`.venv\Lib\site-packages`, CPython 3.14.7).
Project linter (`ruff check src/screens/settings_screen.py`, pyproject rule set) → **All checks passed**.

---

## 1. File role

`SettingsScreen` is a `@ft.component` (`:140`, `:289`) that renders the whole preferences surface of the app as a stack of grouped Material-3 cards inside a `ListView`:

| Card | Lines | Content |
|---|---|---|
| Preferences | `:703-770` | Theme picker (light/dark/system) |
| Scan Parameters | `:773-951` | recursive, permute, extract_info, exclusions, nsfw, allow_loud, show_all, verbose, retries, dns_resolver (desktop-only) |
| Email Intelligence | `:954-1089` | curl_cffi, email timeout/concurrency sliders, only-found, no-pw-recovery, keywords, deep-enrich, domain scopes |
| Cross-Scan | `:1092-1192` | cross-scan switch, links/emails/depth/sweep |
| Phone Intelligence | `:1195-1225` | phone concurrency slider, "silent operation" note |
| Performance | `:1228-1306` | scan depth, max connections, bundled DB, request timeout |
| Custom Manifest | `:1309-1369` | manifest URL/path field |
| About | `:1383-1441` | icon, version, changelog dialog |
| Network & Proxy | `:1444-1525` | proxy URL, I2P, proxy file, Validate, cookies, check-domains (desktop-only) |
| Enrichment | `:1526-1552` | basic/full mode |
| Troubleshooting & Logs | `:1701-1751` | engine-log switch, live terminal, DB health check |

Data flow: UI → `state` (observable, `core/state.py`, read through `AppStateCtx` `:291`) → persisted via `StorageService` under `sherlock_*` keys (`:688-698`) → consumed by `main.py` / `services/*`. `ControllerMethodsCtx` (`:292`) supplies `refresh_sites` and `run_db_health`.

---

## 2. API verification summary

**No hallucinated flet APIs in this file.** Every control, field and enum was instantiated against the installed flet 1.0.4:

| Used at | API | Verdict |
|---|---|---|
| `:975`, `:997`, `:1179`, `:1201`, `:1256`, `:1293` | `ft.Slider(value, min, max, divisions, label, active_color, on_change, on_change_end)` | OK — `on_change_end` exists (`flet/controls/material/slider.py:251`); `value` is `int\|float\|None` |
| `:778`, `:793`, `:815`, `:830`, `:845`, … | `ft.Switch(value, on_change, active_color)` | OK |
| `:905`, `:934`, `:1113`, `:1135`, `:1157`, `:1234`, `:1532` | `ft.SegmentedButton(segments=[ft.Segment(value, label)], selected, on_change, show_selected_icon)` | OK |
| `:1480`, `:1728`, `:1743` | `ft.FilledButton("text", icon=…, on_click=…)` | OK — positional first arg is the label |
| `:1684`, `:1689`, `:1694` | `ft.TextButton("text", icon=…, on_click=…)` | OK |
| `:1563`, `:1584` | `ft.Text(selectable=True, expand=True, weight=, text_align=)` | OK — `selectable` **is** a `Text` property in 1.0.4 (the comment at `:183-184` is correct only about `TextField`, which has no `selectable`) |
| `:1418` | `ft.SelectionArea(content=…)` | OK |
| `:1608` | `ft.AlertDialog(modal=, title=, content=, actions=, actions_alignment=)` | OK |
| `:168` | `ft.TextField(border={ControlState.DEFAULT/FOCUSED: OutlineInputBorder}, text_size=, content_padding=, on_change/on_submit/on_blur)` | OK — `on_submit`/`on_blur` both exist |
| `:206`, `:352`, `:1612` | `ft.Icon(icon, size=, color=)` / `ft.IconButton(icon_size=, icon_color=)` | OK |
| `:263`, `:349`, `:1401` | `ft.Container(ink=, on_click=, tooltip=, clip_behavior=, margin=, padding=)` | OK |
| `:386` | `ft.Animation(duration, curve)` | OK |
| `:1753`, `:1804` | `ft.ListView(controls, spacing, expand)` | OK |
| `:214`, `:283` | `ft.Colors.with_opacity`, `ft.Border.all` | OK |
| `:1388` | `ft.Image(src="/icon.svg", width, height, color=)` | OK — `color` valid; `src/assets/icon.svg` exists |
| `:1698`, `:1560` | `page.show_dialog` / `page.pop_dialog` | OK (both exist on `ft.Page` in 1.0.4) |
| `:140` | `ft.component` | OK (`flet/components/component_decorator.py:10`); callable props are held server-side, so `on_commit=<callable>` (`:1049`, `:1080`) is legal |
| `:303` | `page.platform.is_mobile()` | OK — documented flet 1.0.4 idiom |
| all | 41 distinct `ft.Icons.*`, all `ft.Colors.*` / `ft.FontWeight.*` | OK — every name exists in the 1.0.4 icon/colour DB |

Non-flet deps:
- `user_scanner.core.helpers.validate_proxies(proxy_list, timeout=5, max_workers=50)` is **synchronous** and returns `List[str]` → the `asyncio.to_thread` call at `:668` is correct.
- `user_scanner.core.helpers.parse_email_domain_scopes(value)` returns a **tuple of domains** and **raises `ValueError`** for any token that is not one of the 38 scope keys (`all`, `global`, `usa`, `uk`, …) — `user_scanner/core/helpers.py:86, 477-491`.
- `httpx 0.28.1` supports exactly `http`, `https`, `socks5`, `socks5h` (`httpx/_transports/default.py:187`) — which is precisely the `_PROXY_SCHEMES` list at `:75`.

**Known-context refutations**
- *"SOCKS4/4a rejected at the field"* → **correct behaviour, not a bug.** httpx cannot speak SOCKS4, so rejecting it at `:91-92` is right. (The only defect is that the user learns this by typing, not by reading.)
- *"`:302` reads `page.width` once"* → **confirmed**, see M1.
- *"`:648` reads `state.proxy_file` but no call site passes it to `set_proxy_manager`"* → **confirmed but mis-described**: there is no `set_proxy_manager` anywhere in the repo. The file's proxies are read only by this file's own `_validate_proxies` (`:648-660`) and never reach the engine.
- *"`except TypeError, ValueError:` at `:448` is a syntax error"* → **not a bug here.** It is PEP 758 (unparenthesised `except` groups), legal from **Python 3.14**, and `pyproject.toml` pins `requires-python = ">=3.14"`. It compiles and runs on the installed 3.14.7. It is only a portability trap (see L5).

---

## 3. Settings plumbing table (live / dead)

Consumer column = the engine/service that actually reads the state field. "DEAD" = the field is written and persisted but **no** engine/service reads it.

| # | Control (line) | state field | storage key | Consumer | Status |
|---|---|---|---|---|---|
| 1 | theme cards `:305-387` | `theme_mode` | `STORAGE_THEME` | `main.py:640-647` | LIVE |
| 2 | NSFW switch `:389-403` | `nsfw_enabled` | `STORAGE_NSFW` | `sherlock_service.py:111,113,209` | LIVE |
| 3 | safe-search mirror `:396-398` | `safe_search` | `STORAGE_SAFE_SEARCH` | — | **DEAD** (mirror only, never read) |
| 4 | exclusions switch `:405-409` | `ignore_exclusions` | `STORAGE_EXCLUSIONS` | — | **DEAD** (only a home chip, `home_screen.py:949`) |
| 5 | local DB switch `:411-415` | `use_local_db` | `STORAGE_LOCAL_DB` | — | **DEAD** |
| 6 | manifest field `:417-428` | `custom_manifest` | `STORAGE_MANIFEST` | — | **DEAD** (`sherlock_service.load_sites` never reads it) |
| 7 | email timeout slider `:462` | `email_timeout` | `STORAGE_EMAIL_TIMEOUT` | `main.py:1085,1533` | LIVE |
| 8 | email concurrency slider `:465` | `email_concurrency` | `STORAGE_EMAIL_CONCURRENCY` | `main.py:1086,1535,1776` | LIVE |
| 9 | only-found switch `:471` | `email_only_found` | `STORAGE_EMAIL_ONLY_FOUND` | `results_screen.py:537` | LIVE |
| 10 | no-pw-recovery `:559` | `no_password_recovery` | `STORAGE_NO_PASSWORD_RECOVERY` | `main.py:1534` | LIVE |
| 11 | keywords field `:490` | `search_keywords` | `STORAGE_SEARCH_KEYWORDS` | — | **DEAD** (no KEYWORD-badge producer) |
| 12 | deep-enrich switch `:495` | `deep_enrich` | `STORAGE_DEEP_ENRICH` | — | **DEAD** |
| 13 | domain-scopes field `:632` | `email_domains` | `STORAGE_EMAIL_DOMAINS` | `main.py:1068` (in-memory only) | **HALF-DEAD** — key never restored (H5) |
| 14 | cross-scan switch `:612` | `cross_scan_enabled` | `STORAGE_CROSS_SCAN` | `sherlock_service.py:224`, `email_service.py:375` | LIVE |
| 15 | cross links `:616` | `cross_links` | `STORAGE_CROSS_LINKS` | `sherlock_service.py:225`, `email_service.py:376` | LIVE |
| 16 | cross emails `:620` | `cross_emails` | `STORAGE_CROSS_EMAILS` | `sherlock_service.py:226`, `email_service.py:377` | LIVE |
| 17 | cross depth `:624` | `cross_depth` | `STORAGE_CROSS_DEPTH` | `sherlock_service.py:227`, `email_service.py:378` | LIVE |
| 18 | cross sweep slider `:628` | `cross_sweep` | `STORAGE_CROSS_SWEEP` | `sherlock_service.py:228`, `email_service.py:379` | LIVE |
| 19 | phone concurrency `:636` | `phone_concurrency` | `STORAGE_PHONE_CONCURRENCY` | — (`main.py:1776` passes `email_concurrency`) | **DEAD** |
| 20 | scan depth `:563` | `scan_depth` | `STORAGE_SCAN_DEPTH` | — | **DEAD** |
| 21 | max connections `:468` | `max_connections` | `STORAGE_MAX_CONNECTIONS` | `sherlock_service.py:207,239` | LIVE |
| 22 | timeout slider `:459` | `timeout` | `STORAGE_TIMEOUT` | `sherlock_service.py:206`, `main.py:1774` | LIVE |
| 23 | retries `:592` | `retries` | `STORAGE_RETRIES` | `http_client.py:32-35` | LIVE |
| 24 | dns resolver `:596` | `dns_resolver` | `STORAGE_DNS_RESOLVER` | — | **DEAD** |
| 25 | allow-loud switch `:600` | `allow_loud` | `STORAGE_ALLOW_LOUD` | — (`main.py:1777` hardcodes `False`) | **DEAD** |
| 26 | show-all-results `:604` | `show_all_results` | `STORAGE_SHOW_ALL_RESULTS` | — | **DEAD** |
| 27 | verbose output `:608` | `verbose_output` | `STORAGE_VERBOSE_OUTPUT` | — | **DEAD** |
| 28 | recursive switch `:571` | `recursive_search` | `STORAGE_RECURSIVE_SEARCH` | — (engine always recurses) | **DEAD** (display-only chip) |
| 29 | permute switch `:575` | `permute_enabled` | `STORAGE_PERMUTE` | `main.py:990` | LIVE |
| 30 | extract-info switch `:588` | `extract_info` | `STORAGE_EXTRACT_INFO` | — | **DEAD** |
| 31 | check-domains switch `:521` | `check_domains` | `STORAGE_CHECK_DOMAINS` | — | **DEAD** |
| 32 | engine-logs switch `:579` | `log_engine_logs` | `STORAGE_LOG_ENGINE_LOGS` | `main.py:788,2408` | LIVE |
| 33 | curl-cffi switch `:681` | `use_curl_cffi` | `STORAGE_USE_CURL_CFFI` | `main.py:1087,1536` | LIVE |
| 34 | enrichment mode `:486` | `enrichment_mode` | `STORAGE_ENRICHMENT_MODE` | `main.py:1187` | LIVE |
| 35 | proxy URL field `:475` | `proxy_url` | `STORAGE_PROXY_URL` | `http_client.py:43`, `sherlock_service.py:211` | LIVE |
| 36 | I2P field `:510` | `i2p_proxy` | `STORAGE_I2P_PROXY` | — | **DEAD** |
| 37 | proxy file field `:639` | `proxy_file` | `STORAGE_PROXY_FILE` | — (only `_validate_proxies` in this file) | **DEAD** + never restored |
| 38 | cookies field `:499` | `cookies_path` | `STORAGE_COOKIES_PATH` | `main.py:1204-1210` | LIVE |

**Tally: 38 persisted settings → 15 live, 22 dead (one, #13, half-dead), 1 display-only (#28).**

### Storage keys written here but NEVER restored by `main.py:_load_saved_state`
`main.py:640-847` restores ~35 keys. These three are written by this screen and read by nobody:

| Key | Written at | Restored? |
|---|---|---|
| `STORAGE_EMAIL_DOMAINS` | `:634` | **NO** → the domain-scope setting dies on every restart |
| `STORAGE_PROXY_FILE` | `:641` | **NO** → the proxy-file setting dies on every restart |
| `STORAGE_PHONE_CONCURRENCY` | `:1209` | **NO** → dies on every restart (and is dead anyway, #19) |

(Everything else persisted by this file *is* restored by `main.py`, so persistence is not the problem for the other dead rows — the problem is that no engine reads the field.)

---

## 4. NEW bugs / hallucinations (severity-ordered)

### H1 — 3 unpooled ad requests per render (revenue + flicker) `:1760`, `:1771`, `:1776`
**Confirmed.** `components/banner_ad.py:33-55` exists precisely to prevent this:

> *"A fresh BannerAd per render throws away a live ad (resetting AdMob's own refresh cycle) and flashes the slot, so callers request from this pool by slot key instead of building new controls."*

`build_banner_ad()` (`:93-110`) constructs a **new `fta.BannerAd` control** every call. This screen calls it three times per render, and the screen re-renders on *every* observable state write (each switch toggle, each slider commit) → 3 fresh ad slots + 3 slot flashes per interaction, and the live ad is discarded each time. `_on_theme_change` even calls `clear_banner_pool()` (`:319-322`) — clearing a pool this screen does not use, while leaving its own three banners unpooled.
**Fix:** `pooled_banner_ad("settings-top" | "settings-mid" | "settings-bottom")`.

### H2 — "Health check already running" guard is defeated by re-render `:525-536`
`_health_running = False` is a **plain local of the component function**, not `ft.use_state`. Every re-render re-initialises it to `False` and rebuilds the "Run Check" button with `disabled=False` (`:1743-1747`). `run_db_health` itself writes `state.unhealthy_sites` (`main.py:2275`) → re-render → guard gone. A second click can therefore start a **second concurrent 25-site probe**, and the "already running…" snackbar at `:530` can essentially never fire.
**Fix:** `running, set_running = ft.use_state(False)`.

### H3 — "Custom Site-DB Manifest" is a validated, persisted no-op `:417-428`, `:1309-1369`
The field is validated by `_validate_manifest` (`:104-137`), persisted, and `refresh_sites()` is called (`:426-427`) — but `services/sherlock_service.py:100-125` `load_sites()` never reads `state.custom_manifest` and always calls `load_user_modules()`. `main.py:857`'s docstring claims *"refresh_sites (used by Settings after manifest/DB changes)"* — it is not. The user types a manifest URL, gets a green "accepted" impression, and the site list never changes. Also `state.custom_manifest` is the **only** consumer of `STORAGE_MANIFEST` besides the restore at `main.py:691`.
**Fix:** thread `state.custom_manifest` into `load_sites` and pass it to the upstream module loader; until then, hide the row rather than shipping a no-op.

### H4 — "Email Domain Scopes" accepts values the engine rejects, and silently drops them `:1076-1087`
The subtitle says *"or a custom domain"* and the hint says `"global, usa, proton.me"` (`:1083`). Both are wrong: `parse_email_domain_scopes` raises `ValueError` for any token that is not one of the 38 scope keys (`all`, `global`, `usa`, `uk`, …) — `proton.me` is a *domain inside* the global scope, not a scope. `main.py:1069-1074` swallows the `ValueError` into `domains = []`, so the whole feature quietly does nothing. Worse, `_on_email_domains_change` (`:632-634`) has **no validation at all**, unlike the proxy/manifest/cookies fields in the same file.
**Fix:** validate the comma list against `user_scanner.core.helpers.EMAIL_DOMAIN_SCOPES` in the commit handler, show a snackbar naming the valid scopes, and correct the hint/subtitle (e.g. `global, usa, uk`).

### H5 — Three storage keys are written but never restored `:634`, `:641`, `:1209`
See the table in §3. Concretely: the user sets "Email Domain Scopes" → it works for that session → on the next launch `state.email_domains` is `""` again and the engine never sees the value, while the storage row still holds it. Same for the proxy file and phone concurrency.
**Fix:** add the three keys to `main.py:_load_saved_state`.

### H6 — "Phone Concurrency" slider drives nothing `:636-637`, `:1197-1212`
**Confirmed.** `main.py:1776` passes `concurrency=getattr(state, "email_concurrency", 15)` to `phone_service.search()`. `state.phone_concurrency` is written and persisted but never read by any engine. The label *"Parallel phone checks — lower is stealthier, higher is faster"* is untrue; moving the slider changes email concurrency by accident only if the user also moves the email slider.
**Fix:** `main.py:1776` → `concurrency=getattr(state, "phone_concurrency", 15)`.

### H7 — "Allow Loud Modules" switch drives nothing `:600-602`, `:856-866`
`main.py:1777` hardcodes `allow_loud=False`; no call site anywhere passes `state.allow_loud` (the `allow_loud` parameter in `services/user_scanner_compat.py:123,227,307,395` is never fed from state). The switch writes state + storage and has zero effect on a scan.
**Fix:** pass `allow_loud=getattr(state, "allow_loud", False)` at the call sites.

### H8 — Five further switches are pure UI lies `:604-610`, `:588-590`, `:521-523`, `:405-409`, `:571-573`
`show_all_results`, `verbose_output`, `extract_info`, `check_domains`, `ignore_exclusions` and `recursive_search` have **zero** engine consumers (verified across `src/`, excluding `core/state.py` and the restore block in `main.py`). Their subtitles make concrete promises that are never kept:
- "Show All Results" — *"Include not-found, error and skipped platforms in result lists"* → nothing consumes it.
- "Verbose Output" — *"Show raw endpoint URLs and diagnostic detail in result cards"* → nothing consumes it.
- "Include Disabled Sites" — *"Scan unstable or broken networks"* → only paints a chip in `home_screen.py:949`.
- "Recursive OSINT Search" — the engine unconditionally appends recursive secondaries (`main.py:1371` comment, `sherlock_service` `targets.append`); the switch is display-only.

**Fix:** either wire each of these to the engine, or delete the rows. Six of the ~11 rows in the "Scan Parameters" card are currently cosmetic.

### M1 — No responsive reflow: `page.width` is read once `:302`
```python
narrow = bool(page and getattr(page, "width", None) and page.width < 600)
```
`page.width` is `None` during the first render (no layout has happened yet) → `narrow` is `False` → the **wide** layout is built on phones. `page.width` is not observable state in flet 1.0.4, so the screen does not re-evaluate it on rotate/resize; it only reflows if some unrelated state write triggers a re-render (and even then `page.width` may still be `None` on that pass). The whole `stacked=True` mechanism (`:234-255`) is therefore unreachable on the first paint. **Confirmed.**
**Fix:** `w, set_w = ft.use_state(None)` + a `page.on_resized` handler that sets it, and read `w` instead of `page.width`; or drop the manual flag and use flet 1.0.4's responsive `col={"sm": 12, "md": 6}` on the rows.

### M2 — "Scan Scope & Depth" (All / Top 1k / Top 500) and "DNS Resolver Mode" are no-ops `:563-565`, `:1234-1246`, `:596-598`
`state.scan_depth` is restored (`main.py:750`) and shown in `home_screen.py:445,873` but reaches no engine call; `refresh_sites()` after the change reloads the identical full module list. `state.dns_resolver` is likewise restored (`main.py:804`) and read nowhere. Choosing "Top 500" changes nothing about the scan.

### M3 — Proxy file is validation-only; there is no rotation `:639-641`, `:648-660`, `:1466-1475`
The hint says *"path/to/proxies.txt — one per line for rotation"*, but: (a) the file's lines are merged only into the **validation** list at `:654-658`; (b) the scan uses only `state.proxy_url` (`http_client.py:43`, `sherlock_service.py:211`); (c) the field is never restored (H5). So a proxy file is validated, reported as "N/M OK", and then ignored by the scan.

### M4 — The domain-scope feature is capped at 5 addresses and only runs in username mode `:1076-1087`
`main.py:1084` truncates to `generated[:5]`, and the whole block lives inside the **username** search completion path (`main.py:1066-1110`). A user who picks `all` (38 scopes → hundreds of domains) silently gets 5. The row subtitle mentions username mode but not the cap.

### M5 — `SettingsTextField` commits twice per edit → double site-DB reload `:186-187`
Both `on_submit` **and** `on_blur` call `_commit()`. Pressing Enter and then tapping away commits twice: every field writes to storage twice, and for the manifest field (`:1357-1361`) `refresh_sites()` runs **twice** — two full site-database reloads for one edit.
**Fix:** keep the last committed draft in the component and skip a commit that did not change the value.

### M6 — Restored values are never clamped to the slider ranges `:975-980`, `:997-1002`, `:1179-1184`, `:1256-1261`, `:1293-1298`
`main.py` restores `state.timeout` (`:663-668`), `state.email_timeout` (`:705-717`), `state.max_connections` (`:796`) and `state.cross_sweep` (`:825-828`) with **no clamp**, while the sliders are `[5,60]`, `[5,30]`, `[10,100]`, `[0,10]`. flet 1.0.4 does **not** raise at construction (verified: `ft.Slider(value=100, min=5, max=30)` constructs silently), so the screen renders a thumb outside the track and shows a value the user cannot reproduce by dragging. This screen clamps on *write* (`:459-469`) but not on *read*.

### M7 — `page.pop_dialog()` can close the wrong dialog `:1556-1560`
`_open_terminal` unconditionally pops the top of the **global** dialog stack before showing its own. If the user opens Settings → About → "Version" dialog and then the Live Activity Terminal, the version dialog is dismissed (its state lost) and the terminal is stacked on top. `page.pop_dialog()` should not be used to clear "my" dialog.

### M8 — Page-wide `page.update()` from inside a dialog `:1598`, `:1603`
`_refresh_telemetry` and `_clear_logs` mutate two `Text` controls and then call `page.update()`, which re-serialises the **entire page tree** (every card, every control) on each refresh. The correct flet 1.0.4 call is `log_text.update()` / `telemetry_text.update()`. The slider handlers get this right (`:436`, `:453` use `e.control.update()`); the dialog does not.

### M9 — `_parse_proxy`'s port-range check is unreachable `:99-100`
`urlparse(...).port` already raises `ValueError` for a port > 65535 on Python 3.6+, so it is caught at `:96-98` and the `1 <= port <= 65535` branch can never execute — the message *"port N out of range 1-65535"* is unreachable code.

### M10 — Comma-splitting of `proxy_url` in `_validate_proxies` is unreachable from the UI `:647`
`_parse_proxy` (`:78-101`) accepts exactly one URL, so `state.proxy_url` can never contain a comma; the `raw.split(",")` branch is dead. Only the proxy **file** path can contribute multiple proxies — and those never reach the engine (M3).

### L1 — The inner `ListView` is built and thrown away `:1753-1785`, `:1804-1808`
`content` is a full `ListView` (with its own `spacing=0`/`expand=True`) whose `.controls` list is then unpacked into a second `ListView` at `:1804`. The inner control is pure waste; the three `build_banner_ad()` calls happen while building it, which is also why the ad bug (H1) is easy to miss.

### L2 — Terminal dialog is a hand-rolled 500-line text blob `:1554-1698`
One `ft.Text` holds `"\n".join(500 log lines)` inside a fixed `height=260` column (`:1675`). Each refresh rebuilds the whole string and re-sends it. A `ft.ListView` of one-line rows (each individually selectable/copyable) would scroll natively, render incrementally and match the "Live Activity Terminal" claim better. The 260px fixed height also means a phone sees ~12 lines. `page.pop_dialog()` in `_dismiss` (`:1606`) is also the same stack-pop hazard as M7.

### L3 — `log_count` is a render-time snapshot `:1700`
`f"{log_count} entries recorded"` is computed when the screen renders and never refreshes; the number is stale as soon as a scan starts.

### L4 — Copy-all vs show-500 mismatch `:1562` vs `:1578`
The dialog shows the last 500 lines; "Copy Logs" copies **all** lines (`get_logs()` unbounded). Intentional-looking but undocumented; a user who copies gets more than they saw.

### L5 — PEP 758 `except` syntax `:448`
`except TypeError, ValueError:` is valid **only** on Python ≥ 3.14 (PEP 758). `pyproject.toml` pins `requires-python = ">=3.14"`, so this is not a live bug — but it is a hard break on 3.13 and earlier, and the same pattern is used in `main.py:665,707,722` and `services/http_client.py:33`. Worth normalising to `except (TypeError, ValueError):` for portability.

### L6 — `state.theme_mode` is not restored with `page.theme_mode` `:335-347`
`main.py:640-647` restores the saved theme into `page.theme_mode` but never into `state.theme_mode` (which stays at the class default `LIGHT`, `core/state.py:47`). `_create_theme_card` prefers `page.theme_mode` (`:337`), so the highlight is correct while `page` is available — but the fallback branch (`:339`) would highlight the wrong card, and any other consumer of `state.theme_mode` sees `LIGHT`. Low impact, but the two sources of truth can disagree.

### L7 — `_on_theme_change` clears a pool it does not use `:319-322`
The `clear_banner_pool()` call is correct for a pooled screen; here it evicts *other* screens' live ads (Home/Results) while this screen's own three banners stay unpooled (H1).

---

## 5. Improvements (all flet-1.0.4-verified)

1. **Pool the ads** (H1): `from components.banner_ad import pooled_banner_ad` and use `pooled_banner_ad("settings-1")`, `("settings-2")`, `("settings-3")`. One-line change, removes 3 ad requests + slot flicker per interaction.
2. **Make the health-check guard reactive** (H2): `running, set_running = ft.use_state(False)`; drive the button's `disabled` from `running` instead of mutating `e.control` (which is rebuilt each render).
3. **Use `Slider.label`'s built-in `{value}` interpolation** — flet 1.0.4 documents *"The label … may contain `{value}` which will be dynamically replaced with a current slider value"* (`flet/controls/material/slider.py:95-104`). Replace the hand-rolled `_slider_live` (`:430-440`) with a static `label="{value}s"` / `label="{value}"`, and drop the per-tick `e.control.update()` at `:436`. This removes a chatty round-trip on every drag frame.
4. **Replace the `narrow` flag with flet 1.0.4 responsive layout** (M1): give the setting rows `col={"sm": 12, "md": 6}` inside an `ft.ResponsiveRow`, or at minimum track width with `ft.use_state` + `page.on_resized`. The current code has an entire stacking mechanism (`:234-255`) that is unreachable on first paint.
5. **Validate the domain scopes at commit time** (H4): import `EMAIL_DOMAIN_SCOPES` from `user_scanner.core.helpers` and reject unknown tokens with a snackbar, exactly like `_on_proxy_change` (`:475-484`) and `_on_manifest_submit` (`:417-428`) already do. Also fix the hint to `global, usa, uk` and drop "or a custom domain" from the subtitle.
6. **Give the proxy field real multi-proxy support** (M10/M3): either accept a comma-separated list in `_parse_proxy` (validating each element) and forward the list to the engine, or remove the comma-splitting branch and the proxy-file rotation claim so the UI matches reality.
7. **Use `control.update()` instead of `page.update()`** in the terminal dialog (M8) — `log_text.update()` / `telemetry_text.update()`.
8. **Render the terminal as a `ft.ListView` of rows** (L2) instead of one 500-line `ft.Text`, so the log scrolls natively, updates incrementally, and individual lines can be selected.
9. **Guard the double commit** (M5): store `last_committed` in the `SettingsTextField` component and skip `_commit()` when the draft is unchanged — halves storage writes and stops the double `refresh_sites()` on the manifest field.
10. **Clamp on read, not only on write** (M6): `value=float(min(max(state.timeout, 5), 60))` etc. for every slider, so a corrupt/legacy stored value can never render an unreachable thumb.
11. **Turn the 22 dead rows into real settings or delete them** (H3, H6, H7, H8, M2). A settings screen that contains 22 no-op switches is worse than a shorter one: each one teaches the user a false mental model. Cheapest correct subset: fix the 6 engine call sites (H6, H7, H3, M2 ×2, manifest) and delete the remaining rows, or mark them "coming soon".
12. **Restore the three orphaned storage keys** (H5) — a 6-line change in `main.py:_load_saved_state`.
13. **Add a "reset to defaults" action** — with 38 keys and 22 of them dead, a single "Reset all settings" button is a cheap way to bound the blast radius of the dead keys.
14. **Show the effective value of the `email_timeout` migration**: `main.py:705-717` silently rewrites a stored `10` to `30`; the slider at `:975-980` then shows 30 with no explanation.

---

## 6. Verdict

**Functionally clean API usage, functionally broken settings semantics.**

- **flet API correctness: PASS.** Zero hallucinated controls, fields, enums or icon names; every one of the 41 `ft.Icons.*`, all colours, `page.show_dialog/pop_dialog`, `ft.component` with callable props, and `page.platform.is_mobile()` were verified against the installed flet 1.0.4. `ruff` is clean. The only portability wart is the PEP 758 `except` at `:448`, which is legal on the pinned Python 3.14.
- **Settings plumbing: FAIL.** 22 of 38 persisted settings are dead (persisted, never read by any engine), 3 storage keys are never restored, and 4 settings that *do* reach the engine do so with the wrong value (`phone_concurrency` → `email_concurrency`; `allow_loud` → hardcoded `False`; `scan_depth` → ignored; `custom_manifest` → ignored). The screen is, functionally, a preferences UI for a much smaller set of settings than it presents.
- **Severity profile:** 3 High (unpooled ads → revenue/flicker; defeated health-check guard; manifest no-op), 5 High/Medium dead-setting clusters (domain scopes, phone concurrency, allow-loud, 5 cosmetic switches, 2 more no-ops), 8 Medium/Low (no responsive reflow, unclamped restores, double commit, wrong-dialog pop, page-wide updates, dead code in `_parse_proxy`/`_validate_proxies`, inner ListView waste, hand-rolled terminal), 1 portability note.
- **Known-context check:** `:1760/1771/1776` ad-pool bypass — **confirmed**; `:648` proxy_file — **confirmed** (no `set_proxy_manager` exists in the repo); `:302` `page.width` — **confirmed**; `:75/91-92` SOCKS4 rejection — **refuted as a bug** (correct: httpx supports only http/https/socks5/socks5h); `:1562-1570` hand-rolled terminal — **confirmed**; phone-concurrency slider not consumed — **confirmed**; `STORAGE_EMAIL_DOMAINS` reaching the engine — **partially**: it reaches `main.py:1068` in-memory only, is never restored across restarts, silently swallows invalid scopes, and is capped at 5 generated addresses.
