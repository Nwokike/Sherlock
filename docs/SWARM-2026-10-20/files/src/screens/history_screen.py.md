# Audit: src/screens/history_screen.py

## 1) File role

`HistoryScreen` is a `@ft.component` rendering past searches from `state.history` (newest-first). It hydrates from `StorageService` on mount, clears the unseen badge, supports clear-all with confirmation, swipe-to-delete with undo, tap-to-open-cached, and refresh (re-run). Uses `pooled_banner_ad("history-1")` (line 470) correctly.

## 2) API verification

- flet 1.0.4 APIs used (`ft.Dismissible`, `ft.ValueKey`, `ft.DismissDirection.END_TO_START`, `ft.Alignment`, `ft.Padding`, `ft.Margin`, `ft.Border.all`, `ft.AlertDialog`, `page.show_dialog`/`pop_dialog`) all resolve in installed flet. `EmptyState` is a local component, not flet (correctly imported).
- `context.page` access guarded by try/except (lines 100-103); acceptable.
- `spawn()` from core/tasks returns tracked task; used for fire-and-forget (lines 125, 155, 219, 410).
- `ft.use_effect(_hydrate, [])` and `_clear_unseen` callbacks return None (acceptable; spawn inside).
- Truthiness guard on callable field at line 198 (`controller.open_cached_result and ...`) is always True because the field defaults to a callable; harmless but misleading. Same pattern at line 38? no.

## 3) Data contract + mode round-trip

- Storage is oldest-first JSON; `load_history_entries` reverses to newest-first (storage_service.py:344-358). `_save_to_history` (main.py:2208-2257) upserts oldest-first and caps 50.
- Entry keys: `query`, `username` (compat), `mode`, `found`, `total`, `timestamp` (minute precision). Mode can be `MODE_USERNAME`/`MODE_EMAIL`/`MODE_PHONE`.
- Cap is 50 entries (code), not 30.
- open_cached_result (main.py:1893-2095) handles all 3 modes including phone.
- Re-run dispatch defect: `_on_re_search` (lines 202-219) branches only `MODE_EMAIL` vs else (`start_search` username). A `MODE_PHONE` entry therefore launches the username engine on a phone number. Same defect as home_screen `_run_hist`. `_on_open_history` (lines 193-200) first tries `open_cached_result`, which does handle phone; only the cache-miss fallback is broken.
- mode restore from storage at main.py:695 only accepts username/email, so a persisted phone default mode would not restore as phone (separate main.py issue, not this file).
- Unseen badge: cleared on mount (lines 129-134) by setting `state.history_unseen = 0`. app_shell badge (app_shell.py:797-810) is only rebuilt in the else branch when nav bar is not already a NavigationBar, so unseen-count changes do not propagate to an existing nav bar (freeze bug); this screen's clearing does not force a rebuild either.

## 4) Bugs (severity-ordered)

1. High — Phone history re-run launches wrong engine: `_on_re_search` lines 213-218 has no `MODE_PHONE` branch; phone entries fall to `start_search`. Fix: add `elif mode == MODE_PHONE: await controller.start_phone_search(query)`.
2. High — Swipe-delete persistence reverses order / corrupts storage: line 402 calls `encode_history_entries(state.history)` where state.history is newest-first, but storage contract is oldest-first and `encode_history_entries` does not reverse (storage_service.py:361-367). After a swipe delete, persisted order flips vs load contract. Should pass `list(reversed(state.history))` (or fix encoder). Also cap semantics differ (50).
3. High — Delete undo race: `_on_dismiss` (lines 388-411) spawns persist immediately; `_undo` (lines 230-235) only restores in-memory `state.history`, not storage. If undo is clicked within snackbar window, storage stays deleted. Need persist on undo too.
4. Medium — Hydrate background task mutates controls/state outside flet auto-update: lines 107-125 spawn `_fetch` that calls `state.history.clear()/extend()` without `page.update()`; spawned tasks are not flushed by flet's reactive lifecycle. Inner `except Exception: pass` (lines 122-123) silently defeats hydration. Should call page.update() after mutation and log exception.
5. Medium — Stale/None handling: `history = state.history if state.history else []` (line 104) and entry accesses use `.get` with defaults; okay. But `_infer_mode` trusts `entry.get("mode")` only if dict; fine. `_on_open_history`/`_on_re_search` use `entry.get("query") or entry.get("username", "")`; empty query silently no-ops (lines 196-197, 205-206) — acceptable but no user feedback.
6. Medium — Dismissible key instability: line 421 includes `_relative_time` output (`ts`) in key; relative label changes over time ("5m ago" -> "6m ago"), changing keys and remounting tiles, losing swipe state. Also identity includes found/total. Consider stable key based on query+mode+timestamp raw.
7. Low — Truthiness guard on callable at line 198 is dead-ish (always True); minor readability.
8. Low — Unseen freeze: clearing on mount (lines 129-134) sets state, but app_shell badge not rebuilt for existing nav bar; badge can stay stale until nav bar recreated.

## 5) Improvements

- Add phone branch to `_on_re_search`.
- Fix delete persistence order and undo persistence.
- Make hydrate task flush UI and log errors.
- Replace `encode_history_entries(state.history)` with reversed input or update encoder to reverse.
- Stabilize Dismissible keys using raw timestamp.
- Consider virtualization/pagination for large history (cap 50, minor).
- `_clear_unseen` could force chrome sync; but badge freeze is in app_shell.

## 6) Verdict

Functional but has a phone-mode re-run gap and a storage-order bug on swipe-delete, plus an undo persistence race. Hydrate error handling is silently swallowed. Fix items 1-3 before release.
