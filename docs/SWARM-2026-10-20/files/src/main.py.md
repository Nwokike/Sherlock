# Audit — `src/main.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/main.py` (2,452 lines)
**Audited:** 2026-10-20 · read-only (no file modified)
**Truth source:** installed `flet 1.0.4` (`.venv\Lib\site-packages\flet`), `user-scanner 1.5.2.3`, `phonsint 0.1.0`, `httpx 0.28.1`, CPython 3.14.7
**Env check:** `main.py` compiles clean under 3.14.7; `ruff check src/main.py` → *All checks passed*.

---

## 1) File role

`main.py` is the app entry point **and** the one god-controller. It owns:

| Lines | Role |
|---|---|
| `main.py:14-98` | Imports. Pulls 42 `STORAGE_*` / `MODE_*` constants out of `core/constants.py`, 6 services, `core.state.state`, `core.tasks.spawn`, `state.controller_ctx`. |
| `main.py:104` | Module-level `_AD_SERVICE_REF` dict — a global side-channel to hand `AdService` to the export flow (which has no controller reference). |
| `main.py:107-2393` | `class AppController` — the whole controller. |
| `main.py:107-164` | `__init__`: service handles, `_main_loop`, `_enrich_*` generation counters, `_search_task`, `_history_lock`, render-flusher bookkeeping. |
| `main.py:168-234` | `_kill_all_activity` — the "new search wins" cancel-everything routine (engines, worker tasks, render flusher, foreground service, `state.search_targets` rebind). |
| `main.py:236-247`, `384-389` | `_live_username_progress` / `_live_email_progress` — liveness probes used by the re-attach gates. |
| `main.py:249-337` | `_ensure_notifications_ready`, `_copy_scan_summary`, `_notify_permission_denied`, `_open_notification_settings` — OS-notification lifecycle. |
| `main.py:339-420` | Ownership helpers: `_owns_scan`, `_abandon_search`, `_register_search_task`, `_start/_stop_render_flusher`. |
| `main.py:422-466` | `_render_flusher` — the single ~2 Hz `progress_version` bumper. |
| `main.py:468-633` | `init()` — page configuration, service mounting, `page.render(...)`, Android back-guard (`_guard_root_view_pop`, `_on_root_confirm_pop`). |
| `main.py:635-849` | `_load_saved_state` — the **only** restore path for persisted settings. |
| `main.py:851-879` | `_load_and_cache_sites` — site-DB loader + `STORAGE_CACHED_SITES` warm cache. |
| `main.py:883-1179` | `start_search` (username / sherlock) + all of its exit paths. |
| `main.py:1181-1277` | `_drain_enrich_queue` — streaming profile enrichment. |
| `main.py:1279-1419` | `_progress_from_thread` (worker→main-loop bridge) and `_apply_progress` (progress admission/scoping). |
| `main.py:1421-1452` | `_cancel_task_threadsafe`, `cancel_search`. |
| `main.py:1456-1711` | `start_email_search` / `cancel_email_search`. |
| `main.py:1728-1862` | `start_phone_search` / `cancel_phone_search`. |
| `main.py:1864-2101` | `save_selected_sites`, `set_onboarding_done`, `open_cached_result` (3 mode branches). |
| `main.py:2103-2259` | `_on_username_primary_done` bridge and `_save_to_history` (snapshot + history list). |
| `main.py:2263-2312` | `run_db_health`, `open_update_dialog`, `check_for_updates`. |
| `main.py:2316-2393` | `_show_snack`, `on_error`, connectivity + lifecycle handlers. |
| `main.py:2396-2439` | `async def main(page)` — logging setup, controller construction, `page.on_error` / `on_disconnect` / `on_close`. |
| `main.py:2442-2452` | `__main__` block — `ft.run(main, assets_dir=...)` with a correct `__file__`-relative assets path. |

**Architecturally this file is doing four jobs at once:** page/lifecycle plumbing, settings persistence, three search orchestrators, and a reactive-state bridge. Section 5 lays out the concrete split.

---

## 2) API verification summary

Every flet call site in this file was checked against the **installed** `flet 1.0.4` source tree, never from memory.

### Counts

| Category | Checked | Correct | Broken / unusable | Notes |
|---|---|---|---|---|
| flet **classes / enums / services** | 14 | 13 | 1 | `ft.Clipboard.set_text` does not exist |
| flet **Page properties / events** | 12 | 11 | 1 (dead) | `page.file_picker` is not a flet field |
| flet **methods on installed classes** | 9 | 9 | 0 | `page.render`, `page.update`, `page.run_task`, `View.confirm_pop`, `Connectivity.get_connectivity`, `ft.run(assets_dir=…)`, `Clipboard.get/set` |
| **user-scanner / phonsint** call sites | 4 | 4 | 0 (3 params dropped downstream) | `parse_email_domain_scopes` exists and matches |
| **project service methods** | 14 | 14 | 0 (2 params dropped downstream) | all signatures match |
| **`state.*` attributes** | 72 | 72 | 0 | every one exists in `core/state.py` |
| **`STORAGE_*` constants** | 45 | 45 | 0 (6 never restored) | all exist in `core/constants.py` |

**Hallucinated APIs: exactly one** — `Clipboard.set_text` (`main.py:305`). Everything else in the file resolves to a real installed symbol.

### Verified present and correct (selected)

| Usage (main.py) | flet 1.0.4 source | Verdict |
|---|---|---|
| `ft.Clipboard` `:305` | `controls/services/clipboard.py` | class exists |
| `shared_clipboard(page).set_text(line)` `:305` | `Clipboard` has **only** `set(value)` and `get()` | **FAIL — see B-1** |
| `ft.ThemeMode.SYSTEM/DARK/LIGHT` `:483,642-646` | `controls/base_page.py:169` | OK |
| `ft.Connectivity` `:499` + `on_change` `:500` | `controls/services/connectivity.py` | OK |
| `await connectivity.get_connectivity()` `:2335` | returns `list[ConnectivityType]` | OK — `ft.ConnectivityType.NONE not in result` `:2336` is correct |
| `ConnectivityChangeEvent.connectivity` `:2344` | `controls/services/connectivity.py` | OK |
| `ft.FilePicker()` `:491` | `controls/services/file_picker.py` | OK as a service |
| `page.services.append(...)` `:492,501` | `Page.services` is a list property | OK |
| `page.file_picker = file_picker` `:493` | **not** a `Page` field (64 dataclass fields, no `file_picker`) | **stray attribute — see N-11** |
| `page.render(lambda: …)` `:588` | `controls/page.py:765-775` → writes `views[0].controls` | OK |
| `page.views` `:567,576,606,609` | `controls/base_page.py:159` — `default_factory=lambda: [View()]` | OK — never empty, so `views[0]`/`views[-1]` are the same root |
| `page.on_view_pop` `:587` | `controls/page.py:642` | OK |
| `View.can_pop` `:612`, `View.on_confirm_pop` `:613` | `controls/core/view.py:149,154` | OK |
| `await e.control.confirm_pop(False)` `:631` | `controls/core/view.py:169-185` — coroutine, `should_pop: bool` | OK |
| `page.on_app_lifecycle_state_change` `:508` | `controls/page.py:614-618` | OK |
| `ft.AppLifecycleState.RESUME/.SHOW` `:2361` | `ft.AppLifecycleState` enum | OK |
| `AppLifecycleStateChangeEvent.state` `:2361` | `controls/page.py` | OK |
| `page.on_platform_brightness_change` — **never used** | `controls/page.py:614-618` exists | **exists but unwired — see B-3** |
| `page.on_error` `:2413` | `controls/page.py:695` | OK (payload is a `ControlEvent`, `data` is a *string*) |
| `page.on_close` / `page.on_disconnect` `:2420,2439` | `controls/page.py` | OK — async handlers allowed |
| `page.window.min_width/min_height` `:484-485` | `controls/core/window.py` | OK |
| `page.fonts` `:478`, `page.theme`/`dark_theme` `:479-480`, `Theme.font_family` `:481-482` | `controls/theme.py` | OK |
| `page.run_task(...)` `:507,528,532,535` | `controls/page.py:929-945` — requires a **coroutine function**; all four pass one | OK |
| `page.update()` `:614,1450,1724,1860,2308` | `controls/page.py` | OK |
| `ft.run(main, assets_dir=…)` `:2452` | `flet/__init__.py` — `assets_dir: str \| None` | OK |
| `ft.SnackBarAction` / `ft.Duration` (via `core/notify.py`) | `ft.SnackBarAction` exists | OK |
| `ft.create_context` / `ft.use_context` (via `state/controller_ctx.py`) | `components/context.py` | OK |
| `ft.Brightness.DARK` (via `core/theme.py:132`) | `ft.Brightness` enum | OK |

### Engine / project API verification

| Usage (main.py) | Installed source | Verdict |
|---|---|---|
| `from user_scanner.core.helpers import parse_email_domain_scopes` `:1071` | `user_scanner/core/helpers.py` — `parse_email_domain_scopes(value: str) -> tuple[str, ...]` | **OK, exists, signature matches** |
| `sherlock_service.load_sites(mode="username"/"email")` `:869,873` | `services/sherlock_service.py:100` | OK |
| `sherlock_service.search(username, on_progress, timeout, after_primary)` `:1003-1008` | `services/sherlock_service.py:130-136` | OK — all 4 kwargs match |
| `sherlock_service.run_hudson(target, is_email)` `:1120` | `services/sherlock_service.py:276` | OK |
| `sherlock_service.run_db_health(sample_size=25)` `:2271` | `services/sherlock_service.py:295` — `(*args, **kwargs)` | OK |
| `email_service.load_sites(mode="email")` `:866` | `services/email_service.py:171` | OK — but the `mode` arg is **never used** inside the service |
| `email_service.search(email, on_progress, timeout, skip_password_recovery, concurrency, use_curl_cffi, proxy)` `:1530-1538` | `services/email_service.py:200-213` | OK — all 8 kwargs match |
| `email_service.run_hudson(target, is_email=True)` `:1576` | `services/email_service.py:414` | OK |
| `phone_service.search(phone, region, on_progress, timeout, concurrency, allow_loud, proxy)` `:1771-1779` | `services/phone_service.py:123-133` | signature OK — but **`region` and `proxy` are dropped inside the service** (`phone_service.py:198` passes a hard-coded `None` for region and never forwards `proxy`) |
| `enrich_service.is_available` `:968,1183,1409` | `services/enrich_service.py:16-18` — **hard-coded `False` stub** | **the whole enrichment path is unreachable — see N-1** |
| `enrich_service.enrich_url(url, timeout=, cookies=, user_agent=)` `:1197-1220` | `services/enrich_service.py:26-30` — `(**kwargs)` | OK (moot, see N-1) |
| `schedule_avatar_download(url)` `:1245,1633` | `services/cache_service.py:265` | OK |
| `spawn(coro)` `:312,403,970,1245,1633,2114,2370` | `core/tasks.py` — `asyncio.create_task` + done-callback logging | OK — **but see N-6 for the one place a future is created without a done-callback** |
| `show_snack(page, msg, bgcolor=, duration=, action_label=, on_action=)` `:319-326,2320` | `core/notify.py` | OK |
| `state.*` (72 distinct) | `core/state.py` | OK — all defined |

---

## 3) Confirmed known bugs (verdicts on the sibling list)

| # | Claimed | Verdict | Evidence |
|---|---|---|---|
| B-1 | `main.py:305` `shared_clipboard(page).set_text(line)` — flet Clipboard has set/get only, "Copy report" always raises | **CONFIRMED** | `flet/controls/services/clipboard.py`: the class exposes **`set(value: str)`** and **`get() -> str \| None`** only — no `set_text`/`get_text`. Every other clipboard call site in the repo uses the correct API (`app_shell.py:181`, `components/profile_detail_dialog.py:181`, `screens/settings_screen.py:1577` → `cb.set(...)`; `screens/home_screen.py:739` → `await clipboard.get()`). `main.py:305` is the **only** `.set_text` in the codebase, so the notification's "Copy report" action raises `AttributeError` every time — swallowed by the `except Exception` at `main.py:309`, which only logs a WARNING. Fix: `await shared_clipboard(self.page).set(line)`. |
| B-2 | `main.py:483` `page.theme_mode = SYSTEM` without `page.on_platform_brightness_change` wiring | **CONFIRMED** | flet 1.0.4 exposes `Page.on_platform_brightness_change` (`controls/page.py:614-618`) and `Page.platform_brightness` (`controls/page.py:571`); `core/theme.py:129-133` `is_dark_mode()` resolves `ThemeMode.SYSTEM` **solely** through `page.platform_brightness == ft.Brightness.DARK`. `grep` shows `on_platform_brightness_change` is referenced **nowhere** in `src/`. Consequence: an OS theme flip while the app is idle mutates no observable state → no re-render → the palette stays stale until an unrelated state change forces a redraw. The stored `"system"` preference (`main.py:644`) is the same hole. |
| B-3 | `main.py:2426-2428` swallows teardown exceptions | **CONFIRMED (low severity)** | `main.py:2422-2437`: four separate `with contextlib.suppress(Exception):` blocks wrap `storage.flush()`, `ad_service.close()`, `scan_notify.shutdown()` and `close_client()`. The `ad_service.close()` block (`:2426-2428`) discards a real failure with zero trace. Note the file *does* explain the http_client case (`:2432-2433`: "logs its own failures at WARNING") — so the suppress there is deliberate, but the `ad_service.close()` one is not, and `AdService.close()` is the only teardown that can leave an ad impression unreleased. Recommend: log at ERROR instead of suppressing, or at minimum `logger.exception`. |
| B-4 | `main.py:2322` `on_error` swallows errors into a generic snackbar | **PARTIALLY CONFIRMED** | It does not fully swallow — `main.py:2324` logs `logger.error("Page error: %s", getattr(e, "data", e))`. But the flet `on_error` payload is a `ControlEvent` whose `data` is a **string** (`controls/page.py:695`), so there is no exception object and **no traceback is ever captured**. The user only ever sees `ERR_GENERIC`, and `state.search_error` is *not* set, so the Results screen shows no error state. Compare the per-mode handlers at `main.py:1158-1174` and `main.py:1694-1710`, which classify network-vs-generic **and** record `state.search_error`. `on_error` should do the same. |
| B-5 | `main.py:1120-1123` / `:1576-1579` display raw ANSI strings from the hudson capture | **CONFIRMED (and worse than stated)** | `user_scanner/core/hudson.py:5-12` builds output from `colorama.Fore.*` / `Style.RESET_ALL` with **no `colorama.init()` and no ANSI stripping**; `services/sherlock_service.py:276-289` and `services/email_service.py:414-427` capture that stdout verbatim into a `StringIO` via `contextlib.redirect_stdout`. `main.py:1123` / `main.py:1579` then put the raw escape sequence into a snackbar (`hudson_out[:120] + "..."` can slice mid-escape). **Additional defect not in the sibling list:** `hudson.run_hudson_scan` → `check_hudson_permission` (`user_scanner/core/hudson.py:23-48`) calls **`input()`** for a `y/n/d` consent prompt. The prompt text is swallowed by the same `redirect_stdout` (never shown), and the call blocks on stdin. `main.py:1119` / `main.py:1575` `await asyncio.to_thread(...)` it, so the **whole `start_search` / `start_email_search` coroutine hangs at the end of every Hudson-enabled scan** (in a packaged desktop build stdin is usually closed → `EOFError` → the string `"Hudson check failed: …"`). A consent prompt the user can never answer, and a third-party OSINT call the user cannot decline, is a privacy/UX bug as well as a hang risk. |
| B-6 | `main.py:1776` `email_concurrency` passed for phone scans | **CONFIRMED** | `main.py:1776` `concurrency=getattr(state, "email_concurrency", 15)`. `state.email_concurrency` is the **email** setting (`main.py:715-728` restores it from `STORAGE_EMAIL_CONCURRENCY`, and the migration at `:723-728` forces the default down to **5**). The phone engine therefore runs at concurrency 5 while the UI's phone-concurrency slider is ignored. |
| B-7 | `main.py:1773` `region` hardcoded `None` | **CONFIRMED, and the root cause is deeper** | `main.py:1773` passes `region=None`; **but `PhoneService.search` drops the argument anyway** — `services/phone_service.py:198` calls `self._run_worker, phone, None, modules, …`, i.e. a hard-coded `None` that ignores the `region` parameter accepted at `phone_service.py:126`. So this is a **two-site bug**: fixing `main.py` alone would change nothing. Impact: phonsint's region is the default ISO country code for numbers without a `+` prefix (`phonsint/core/parser.py:19-30`, falling back to `"US"`), so a local-format non-US number is parsed as US and matches no module. |
| B-8 | `main.py:1778` proxy passed but never used by `phone_service` | **CONFIRMED** | `proxy` appears in `services/phone_service.py` **only** in the signature (`:131`); it is not forwarded to `_run_worker` (`:198`) and not read anywhere in the body. The user's `state.proxy_url` is silently ignored for phone scans. (The email path *does* honour it — `services/email_service.py:238-247` injects proxy env vars.) |
| B-9 | `main.py:2203` / `:835-842` cache unbounded (790 KB+) | **CONFIRMED in substance, mis-stated in mechanism** | `state.set_cached_result` (`core/state.py:173-180`) caps the **entry count** at 30, but nothing caps the **size**. `main.py:2203` serialises the *entire* cache — up to 30 full snapshots, each with a `not_found` list of up to ~500 site dicts plus an `enrichments` dict — into **one** storage key, and `main.py:835-842` `json.loads()`s that whole blob back at startup. Both `json.dumps` (`:2203`) and `json.loads` (`:838`) run **synchronously on the UI event loop**. The write happens on **every** history save, and a username scan saves **twice** (`main.py:1107` final + `main.py:2114` primary-done bridge) → two full serialisations of a multi-MB blob per scan. Secondary defect: `main.py:840` `state.results_cache.update(res_map)` bypasses the 30-entry LRU cap of `set_cached_result`, so a restored blob with >30 entries stays over cap forever. |
| B-10 | `main.py:588` single-view render; `page.views[-1]` usage | **REFUTED as a bug** | flet 1.0.4 guarantees a non-empty view stack: `controls/base_page.py:159` `views: list[View] = field(default_factory=lambda: [View()])`. `Page.render` (`controls/page.py:765-775`) writes `self.views[0].controls`, and with a single view `views[-1] is views[0]` — so `main.py:609` `root = views[-1]` is the same object the renderer populated. `_guard_root_view_pop` (`:593-617`) therefore patches the correct `View`. `main.py:610` `getattr(root, "can_pop", True) is False` correctly detects a re-entered init. No defect here. |
| B-11 | `main.py:587` / `:606-614` view-stack handling | **REFUTED as a bug (one narrow race, see N-19)** | `page.on_view_pop` is a real flet field (`controls/page.py:642`). The app does **not** use flet's `Router` (no `Router` anywhere in `app_shell.py`), so `components/router.py:670-718` never overwrites `page.on_view_pop` — the app's handler stands. The only gap: `methods.handle_system_back` is assigned inside AppShell's body (`app_shell.py:743`), and `Renderer.render` only *constructs* the component tree — the body runs in flet's component scheduler, so for the first frame `handle_system_back` is still the `_noop_sync` default from `state/controller_ctx.py`. A back press in that window is swallowed. Cosmetic, but real. |

---

## 4) NEW bugs / hallucinations (severity-ordered)

### N-1 · CRITICAL — the entire enrichment subsystem in `main.py` is unreachable

`EnrichService.is_available` is a **hard-coded `False` stub**: `src/services/enrich_service.py:15-18` (`self._available = False`; `@property is_available → return False`), and the module docstring says *"Enrichment becomes a no-op"*. Every enrichment branch in `main.py` is therefore dead:

| Location | Guard | Effect |
|---|---|---|
| `main.py:968` | `if self.enrich_service and self.enrich_service.is_available:` | the drain worker is **never spawned** |
| `main.py:1183` | `if not self.enrich_service or not self.enrich_service.is_available: return` | the worker would exit immediately |
| `main.py:1409-1414` | `self.enrich_service.is_available` | **no URL is ever enqueued** |
| `main.py:1224-1246` | — | `_pending_enrichments` / avatar warming unreachable |
| `main.py:438-447`, `main.py:412-417` | — | the flusher's enrichment batch is always empty |
| `main.py:1991`, `:2016`, `:2068` | `state.enrichments.clear()` | always a no-op |
| `main.py:2184` | `"enrichments": dict(state.enrichments or {})` | always `{}` in history snapshots |

Dead state that exists only to serve it: `_enrich_queue` (`:135`), `_enriched_seen` (`:136`), `_enrich_worker_task` (`:137`), `_enrich_gen` (`:142`), `_avatar_warmed` (`:144`), `_pending_enrichments` (`:163`) — plus `state.enrichment_mode` (`:735-742`, `:1187`), whose "basic vs full" setting has no effect at all, and `_drain_enrich_queue` (`:1181-1277`, 97 lines).

**Impact:** ~120 lines of controller code plus 6 instance attributes are unreachable; the Enrichment feature advertised by `state.enrichment_mode` is a no-op. The email avatar-warming path (`main.py:1624-1638`) is *not* affected — it calls `schedule_avatar_download` directly.

### N-2 · HIGH — `_load_saved_state` never restores 6 persisted settings; they silently reset on every restart

`main.py:635-849` is the **only** restore path, and it omits 6 keys that the UI *does* persist:

| Constant | Persisted by | Consumed by `main.py` | Effect of the omission |
|---|---|---|---|
| `STORAGE_HUDSON` | `screens/home_screen.py:568` | `main.py:1117`, `main.py:1573` (`state.hudson_enabled`) | the Hudson Rock OSINT never runs after a restart, even if the user enabled it |
| `STORAGE_EMAIL_DOMAINS` | `screens/settings_screen.py:634` | `main.py:1068` (`state.email_domains`) | the email-domains scan (`main.py:1067-1105`) is skipped after a restart |
| `STORAGE_PHONE_CONCURRENCY` | `screens/home_screen.py:477` | — (and `main.py:1776` uses the email value instead) | the phone concurrency slider is dead |
| `STORAGE_SHOW_ALL_RESULTS` | `screens/settings_screen.py:606` | — | resets every launch |
| `STORAGE_VERBOSE_OUTPUT` | `screens/settings_screen.py:610` | — | resets every launch |
| `STORAGE_PROXY_FILE` | `screens/settings_screen.py:641` | — | resets every launch |

(`STORAGE_BULK_MODE` is the 7th never-restored key, but it is never written either — genuinely unused.)

**Impact:** six user-visible preferences silently revert on every app start. This is a class-level gap: the restore path was written per-key by hand and never reconciled against `core/constants.py`.

### N-3 · HIGH — phone engine receives the wrong settings (`allow_loud`, `concurrency`, `region`, `proxy`)

`main.py:1771-1779`:
* `region=None` (`:1773`) — see B-7 (double-dropped).
* `concurrency=getattr(state, "email_concurrency", 15)` (`:1776`) — see B-6.
* **`allow_loud=False` (`:1777`) — hard-coded.** `state.allow_loud` is restored at `main.py:810-812` and honoured by the *other two* engines (`services/sherlock_service.py:208,240`; `services/email_service.py:364,393`), but the phone path overrides it with a literal `False`. The "Loud" toggle on the home screen therefore has **no effect on phone scans**, and it is the one place in the file where a state setting is deliberately overridden with a constant.
* `proxy=getattr(state, "proxy_url", "") or ""` (`:1778`) — see B-8.

### N-4 · HIGH — `json.dumps` of the whole result cache on the UI loop, twice per scan, plus a load-time race

* `main.py:2203` `await self.storage.set(STORAGE_CACHED_RESULTS, json.dumps(state.results_cache))` — the whole cache (≤30 snapshots × ~500 site dicts each) is serialised **synchronously on the event loop** on every history save. A username scan saves twice (`main.py:1107` and the primary-done bridge `main.py:2114`) → two multi-MB serialisations per scan, each a UI freeze.
* `main.py:835-842` — the same blob is `json.loads()`-ed at startup, also on the loop, blocking first paint.
* `main.py:840` — `state.results_cache.update(res_map)` bypasses the 30-entry LRU of `state.set_cached_result` (`core/state.py:173-180`).

### N-5 · HIGH — race: concurrent `json.dumps` over a mutating dict silently loses the result snapshot

The snapshot block (`main.py:2126-2206`) is **not** under `self._history_lock`; only the history list read-modify-write (`main.py:2222-2237`) is. The primary-done bridge (`main.py:2113-2114`) and the final save (`main.py:1107`) can therefore run concurrently, and both call `state.set_cached_result(...)` (which mutates the dict) and `json.dumps(state.results_cache)`. `json.dumps` on a dict being mutated concurrently raises `RuntimeError: dictionary changed size during iteration`, which the `except Exception as snap_exc` at `main.py:2205` swallows to a WARNING — **the cached result is lost silently** while the history entry still saves. The `_history_lock` must cover the snapshot, or the dump must be taken from an immutable copy.

### N-6 · HIGH — unretrieved future in the worker→loop progress bridge can silently kill progress ticks

`main.py:1309-1317`:
```python
self._main_loop.call_soon_threadsafe(
    lambda: self._main_loop.call_later(delay, lambda: asyncio.run_coroutine_threadsafe(_flush(), self._main_loop)))
)
...
asyncio.run_coroutine_threadsafe(_flush(), self._main_loop)
```
`asyncio.run_coroutine_threadsafe` returns a **`concurrent.futures.Future`**, which — unlike an `asyncio.Future` — **does not log unretrieved exceptions**. If `_flush()` raises (e.g. `_apply_progress` at `:1303` throws), the exception is stored on a future nobody ever reads → it is lost entirely, **and** `self._render_dirty = True` (`:1304`) never runs, so the render flusher has nothing to flush. Result: the UI can freeze mid-scan with no error and no recovery. The file already has the right primitive — `core.tasks.spawn` attaches a logging done-callback — but `spawn` is main-loop-only, so the fix is to schedule `_flush` on the loop and attach a done-callback that logs.

### N-7 · MEDIUM-HIGH — the email-domains branch causes a full-tree re-render storm and inconsistent counters

`main.py:1080-1103`:
* `main.py:1080` `state.email_results = []` — **replaces** the `ObservableList` object, so any component holding the previous list reference goes stale (flet wraps the new list, but the identity changes).
* `main.py:1091` `state.email_results.append({...})` — **one append per result row**. `flet/components/observable.py` `ObservableList.append` calls `_touch()` → `state._notify("email_results")` → every subscriber re-renders the **whole component tree**. With 5 addresses × N modules that is hundreds of full-tree re-renders on the main loop, during a scan. The email path does it correctly with a single bulk write at `main.py:1605` (`state.email_results[:] = all_results` → one `__setitem__` → one touch).
* `main.py:1098-1103` — `state.email_results_address` and all four counters are overwritten **inside** the per-address loop, so the counts describe only the **last** address while `state.email_results` holds the union of all five. The UI's "found / not found" numbers disagree with the row list.

### N-8 · MEDIUM — the exception/CancelledError handlers use target equality instead of scan ownership

`main.py:1150` (`except Exception`) and `main.py:1137` (`except asyncio.CancelledError`) guard on `state.current_username == target_clean` only. The file's own comment at `main.py:1019-1025` states the rule explicitly: *"Target equality alone is not ownership … a dying scan that only compares names would then clear the live replacement's flags."* The success path honours this with `self._owns_scan()` (`main.py:1026`, `main.py:1553`, `main.py:1786`), but the **failure** paths do not. The retry button and a history re-search both start a scan for the **same target** (that is the exact case the comment describes), so a dying same-target scan will still clear the live replacement's `state.is_searching`, stop its render flusher and retract its foreground service. Same for the email path (`main.py:1660`, `main.py:1674`, `main.py:1686`) and the phone path (`main.py:1835`).

### N-9 · MEDIUM — `state.theme_mode` is never restored, so the header theme control shows the wrong state

`main.py:640-646` restores `page.theme_mode` from storage but **never sets `state.theme_mode`** (`core/state.py:38`, default `ThemeMode.LIGHT`). `app_shell.py:842` and `components/app_header.py:112-127` read/write `state.theme_mode`. After a restart with a dark theme the header's theme control still renders "light" until the user cycles it once. `screens/settings_screen.py:314-315` and `components/app_header.py:127` both set page **and** state — `main.py`'s restore path is the only one that doesn't.

### N-10 · MEDIUM — `page.on_platform_brightness_change` is never wired (see B-2) — OS theme changes don't repaint

### N-11 · MEDIUM — `page.file_picker` is a non-flet attribute; the registered FilePicker is dead

`main.py:491-493`:
```python
file_picker = ft.FilePicker()
self.page.services.append(file_picker)
self.page.file_picker = file_picker
```
`page.file_picker` is **not** a `Page` dataclass field in flet 1.0.4 (verified: 64 fields, no `file_picker`) and `Page.__setattr__` is the plain `object.__setattr__` slot wrapper, so the assignment silently creates a stray attribute on the instance. Nothing in the repo reads `page.file_picker`; `app_shell.py:420-421` builds its **own** `ft.FilePicker()` inline — precisely the pattern `main.py:488-490`'s own comment warns against ("Constructing it inline per-call loses the registration on Android"). Net effect: `main.py` registers a FilePicker service nobody uses, and the real export flow still uses an unregistered one.

### N-12 · MEDIUM — `_load_and_cache_sites` calls `self.sherlock_service.load_sites(...)` with no None guard in the email branch

`main.py:863-869`:
```python
elif state.search_mode == MODE_EMAIL:
    if not self.email_service: return
    count = await self.email_service.load_sites(mode="email") if hasattr(self.email_service, "load_sites") else 0
    if not count:
        count = await self.sherlock_service.load_sites(mode="email")   # <-- no None check
```
The `else` branch (`:870-872`) *does* check `if not self.sherlock_service: return`. `self.sherlock_service` is `None` until `main.py:514`, so the asymmetry is a latent `AttributeError`. Also `hasattr(self.email_service, "load_sites")` at `:866` is **always True** (the method exists at `services/email_service.py:171`) — dead defensive code that hides the real contract; and `email_service.load_sites` **ignores its `mode` argument entirely** (`services/email_service.py:171-190` never reads it), so the `mode="email"` at `:866` is decorative.

### N-13 · MEDIUM — the Hudson Rock consent prompt can hang the search task (see B-5) and leaks a third-party call the user cannot decline

### N-14 · LOW-MEDIUM — `_live_email_progress` also returns `True` for a live **phone** scan

`main.py:384-389` only checks `hasattr(prog, "checked_modules")` — but `PhoneSearchProgress` has `checked_modules` too (`services/phone_service.py:42`). It is only saved by the `state.search_mode == mode` guard at `main.py:1910`, and by `state.search_mode == MODE_EMAIL` at `main.py:1472`. Today it is harmless, but the name promises an email-only predicate and it does not deliver one. `start_phone_search` (`main.py:1728-1741`) also has **no smart re-attach gate**, unlike username (`:902-911`) and email (`:1468-1477`) — a double-tap always kills and restarts the phone scan.

### N-15 · LOW — `except TypeError, ValueError:` is a Python-3.14-only spelling (PEP 758)

`main.py:664`, `main.py:702`, `main.py:719` (and `components/update_dialog.py:228`, `screens/settings_screen.py:448`, `services/http_client.py:33`). **Not a live bug** — `pyproject.toml` pins `requires-python = ">=3.14"` and the venv is 3.14.7, where PEP 758 makes the parentheseless multi-exception form legal. But it reads like a Python-2 typo and is a hard 3.14 dependency: on 3.13 the module fails to import with a `SyntaxError` at parse time, not a runtime error. Worth a `except (TypeError, ValueError):` normalisation pass.

### N-16 · LOW — `_drain_enrich_queue`'s trailing gather is unreachable (moot given N-1)

`main.py:1275-1277`: the `while` loop at `main.py:1250-1273` only exits when `pending_tasks` is empty, so `await asyncio.gather(*pending_tasks, return_exceptions=True)` always gathers an empty set.

### N-17 · LOW — `on_error` never records `state.search_error` (see B-4)

### N-18 · LOW — `state.results_cache` restore bypasses the LRU cap (see B-9)

### N-19 · LOW — the Android back handler is a no-op for the first render frame

`main.py:563-585` registers `_on_system_back` at `:587` **before** `page.render(...)` at `:588`. `flet/components/component.py` `Renderer.render` invokes the root callable synchronously, but that root only *constructs* `AppShell()`; the component body (which assigns `controller.handle_system_back = _system_back`, `app_shell.py:743`) runs later in flet's component scheduler. For that first frame `methods.handle_system_back` is still `_noop_sync` (`state/controller_ctx.py`), so the press is swallowed. Harmless in practice (the frame is sub-100 ms), but it means the `can_pop=False` guard is installed before the app can handle back.

### N-20 · LOW — `main.py:1194` `gen != self._enrich_gen` guard placement is wrong inside `_enrich_single`

`main.py:1192-1195`: the generation check happens **after** acquiring the semaphore but is correct in intent. However the check at `main.py:1221` (`if data and gen == self._enrich_gen`) is the only one that guards the *write*; the `await fn(...)` at `:1215-1220` is not cancellable, so an in-flight enrichment from a killed generation still runs to completion (8 s timeout each). The comment at `main.py:140-141` claims "orphaned `_enrich_single`/avatar tasks can never contaminate the next scan" — that is true for the *state write* but not for the *network work*. (Dead code overall per N-1.)

---

## 5) Improvement opportunities (concrete, ordered)

**I-1 · Delete the enrichment subsystem, or gate it behind a real capability check (fixes N-1, N-16, N-20).**
Concretely: delete `main.py:1181-1277` (`_drain_enrich_queue`), the `_enrich_*`/`_avatar_warmed`/`_pending_enrichments` attributes (`:135-144`, `:163`), the `is_available` guards at `:968`, `:1183`, `:1409-1414`, the enrichment batch in the flusher (`:438-447`), and the `state.enrichments.clear()` calls (`:1991`, `:2016`, `:2068`). That removes ~140 lines and six attributes. If enrichment is meant to come back, keep it but replace `is_available` with a real probe and make `EnrichService` a protocol the future implementation satisfies.

**I-2 · Make `_load_saved_state` table-driven instead of hand-written per key (fixes N-2).**
`main.py:635-849` is 215 lines of `raw = await self.storage.get(...); if raw: try: ... except: ...`. Replace with a declarative spec list of `(STORAGE_KEY, coercion, target)` and a single loop, so a new constant is picked up automatically. At minimum add the six missing keys in N-2 and add a test that asserts "every `STORAGE_*` constant that is written somewhere is read by `_load_saved_state`" — that single test would have caught all six.

**I-3 · Extract one `_run_scan` skeleton for the three modes (fixes N-8, and shrinks ~400 lines).**
`start_search` (`:883-1179`), `start_email_search` (`:1456-1711`) and `start_phone_search` (`:1728-1847`) are the same 8-step ritual: re-attach gate → offline gate → validate → kill → register task → set mode/flags/progress → ensure notifications → interstitial → engine call → completion/supersede/cancel/error exit. The three implementations differ only in the service call and the result→dict mapping. Extracting a shared `_scan_lifecycle(mode, target, progress_obj, engine_call, map_results)` with a `mode` token would let all three share the *ownership* rule (`self._owns_scan()`), which is exactly where N-8 lives.

**I-4 · Centralise the three cancel methods (fixes the triplication).**
`cancel_search` (`:1437-1452`), `cancel_email_search` (`:1713-1726`) and `cancel_phone_search` (`:1849-1862`) are byte-identical apart from the log string. One `_cancel_current_scan(reason: str)` removes 30 lines and the risk of them drifting.

**I-5 · Bound and shard the result cache (fixes N-4, N-5, B-9).**
Three concrete moves: (a) write each cached snapshot under its **own** key (`f"results:{mode}:{query}"`) instead of one monolithic `STORAGE_CACHED_RESULTS` blob, so a save is O(1) instead of O(entire cache); (b) cap the persisted snapshot (drop `not_found` beyond the first N, cap `enrichments` to `_ENRICHMENT_CAP`) — the UI never renders 500 `not_found` rows; (c) move the `json.dumps` off the event loop (`await asyncio.to_thread(json.dumps, ...)`) and take the dump from `dict(state.results_cache)` (a shallow copy) so the concurrent-mutation race in N-5 disappears.

**I-6 · Attach a done-callback to every `run_coroutine_threadsafe` (fixes N-6).**
`main.py:1312` and `main.py:1317` both drop the future. Wrap the coroutine so a done-callback logs the exception, mirroring `core/tasks.py:spawn`.

**I-7 · Batch the email-domains writes (fixes N-7).**
Change `main.py:1080-1103` to accumulate rows in a plain list and write once with `state.email_results[:] = rows` (the pattern already used at `main.py:1605`); move the counters **out** of the per-address loop so they describe the union.

**I-8 · Fix the phone call-site arguments and the service (fixes N-3, B-6, B-7, B-8).**
`main.py:1773-1778` should pass `region=state.phone_region`, `concurrency=state.phone_concurrency`, `allow_loud=state.allow_loud`, `proxy=state.proxy_url`; and `services/phone_service.py:198` must forward `region` and `proxy` instead of the hard-coded `None`. Until `services/phone_service.py` is fixed, the `main.py` change alone is cosmetic — flag it in the issue.

**I-9 · Strip ANSI from the Hudson output and pre-answer the consent prompt (fixes B-5/N-13).**
In `main.py:1122-1123` and `main.py:1578-1579`, run the captured text through a regex strip (`re.sub(r"\x1b\[[0-9;]*m", "", out)`) before displaying it. Better: don't call `user_scanner.core.hudson.run_hudson_scan` (which prompts) at all — call the underlying API yourself with the consent already collected in-app, so the scan cannot block and the privacy notice is visible.

**I-10 · Wire `page.on_platform_brightness_change` (fixes B-2/N-10).**
In `init()` next to `main.py:508`, add a handler that sets `state.theme_mode` from `e.brightness` and bumps `state.progress_version`, so `core/theme.py:129-133` `is_dark_mode()` tracks the OS. Also set `state.theme_mode` in the same place `main.py:640-646` sets `page.theme_mode` (fixes N-9 in the same three lines).

**I-11 · Drop the dead FilePicker registration (fixes N-11).**
Delete `main.py:491-493` (the `page.file_picker` attribute is not flet), and either export `file_picker` on the controller so `app_shell.py:420` can reuse the registered instance, or accept the inline construction and delete the contradicting comment.

**I-12 · Reduce nesting in `_load_saved_state` and `_save_to_history` (structure).**
`main.py:635-849` is one 215-line `try:` with 30 `try/except` blocks nested two deep; `_save_to_history` (`:2121-2259`) similarly. Both are textbook candidates for the table-driven / helper-function split of I-2 and I-5.

**I-13 · Extract the three identical "big result dict" builders (structure).**
`main.py:2134-2183` (username found/not_found/errors → dict), `main.py:1585-1604` (email rows) and `main.py:1803-1817` (phone rows) are three hand-rolled `getattr` chains over the same shape. One `_site_result_to_dict(r)` / `_engine_result_to_dict(r)` pair of helpers would remove ~90 lines and the chance of a field-name drift (the email and phone dicts use *different* keys for the same concept — `domain` vs `category` — which is exactly the kind of drift that produced `main.py:1999-2007`'s fiddly `not r.get("unavailable")` filters).

**I-14 · Make `state.results_cache` the single source for the LRU (fixes N-18).**
`main.py:840` should call `state.set_cached_result` semantics (or a `state.load_cached_results(map)` helper) instead of `state.results_cache.update(res_map)`, so the 30-entry cap is enforced on the restore path too.

---

## 6) Verdict

**ISSUES FOUND**

| Severity | Count | IDs |
|---|---|---|
| Critical | 1 | N-1 |
| High | 5 | N-2, N-3, N-4, N-5, N-6 |
| Medium-High | 1 | N-7 |
| Medium | 6 | N-8, N-9, N-10, N-11, N-12, N-13 |
| Low-Medium | 1 | N-14 |
| Low | 6 | N-15, N-16, N-17, N-18, N-19, N-20 |
| **Total NEW findings** | **20** | |
| **Known-bug list confirmed** | **9** | B-1, B-2, B-3, B-4 (partial), B-5 (+1 extra), B-6, B-7 (+root cause), B-8, B-9 |
| **Known-bug list refuted** | **2** | B-10, B-11 (one narrow race, N-19) |
| **Hallucinated APIs** | **1** | `Clipboard.set_text` (`main.py:305`) — the only fabricated symbol in the file |
| **Dead-code paths** | **4** | enrichment subsystem (N-1); FilePicker registration (N-11); `hasattr` guard at `:866`; trailing gather at `:1276` |

**Verdict: ISSUES FOUND — 20 new findings, 9/11 sibling findings confirmed, 2 refuted, 1 hallucinated API.**

The file is *not* broken at import time: it compiles clean on 3.14.7 and passes `ruff`. The failures are behavioural, not syntactic. The three that matter most for a V3 refactor are:

1. **N-1** — a fifth of the controller (the whole enrichment path, ~140 lines) is unreachable because `EnrichService.is_available` is a stub returning `False`. Refactoring around it will preserve dead weight unless it is removed first.
2. **N-2** — the settings restore path is hand-written per key and is missing 6 of the 47 `STORAGE_*` constants that the UI writes. Every one of those preferences silently resets on restart.
3. **N-3 / B-6 / B-7 / B-8** — the phone engine is wired with the *email* concurrency, a hard-coded `allow_loud=False`, no region, and a proxy the service discards. The phone path is the least-tested branch in the file and the least correct.

**No file was modified.** Every claim above is anchored to a `src/main.py:<line>` (or named sibling file) reference and was checked against the installed `flet 1.0.4` / `user-scanner 1.5.2.3` / `phonsint 0.1.0` sources rather than recalled API knowledge.
