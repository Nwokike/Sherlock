# Sherlock v2 Perfect — Dependency Utilization Checklist

**Branch:** `feature/v2-perfect` → `main` · **Flet 0.86.5** · **Date 2026-08-31**
**Companion:** [docs/v2-audit.md](v2-audit.md) — predecessor audit.

---

## Flet 0.86.5 Surface

| Control / Service | Status | Where |
|---|---|---|
| `SegmentedButton` | ✅ | `home_screen.py` — Username / Email pill |
| `Chip` | ✅ | `home_screen.py` category chips, `results_screen.py` method filter, `settings` toggles |
| `BottomSheet` | ✅ | `app_shell.py` export chooser (`show_drag_handle`) |
| `Banner` | ✅ | `home_screen.py` offline banner (replaced Container) |
| `Slider` | ✅ | `settings_screen.py` — timeout + email timeout + concurrency |
| `Tooltip` | ✅ | `app_shell.py` app bar actions |
| `SelectionArea` | ✅ | `result_card.py` detail column (long-press select) |
| `Markdown` | ✅ | `update_dialog.py` release notes (`GITHUB_WEB`) |
| `SearchBar.controls` | ✅ | `home_screen.py` — 5 recent typeahead |
| `HapticFeedback` | ✅ | `home_screen.py` search, `app_shell.py` copy/share |
| `Share` | ✅ | `app_shell.py` share 20 URLs |
| `Dismissible` | ✅ | `history_screen.py` swipe-to-delete |
| `CardTheme/ChipTheme/ScrollbarTheme/TabBarTheme/PageTransitionsTheme` | ✅ | `core/theme.py` AppTheme |
| `ExpansionTile` | ⬜ | Deferred — settings already grouped via cards |
| `DataTable` | ⬜ | Deferred — results already virtualized ListView |
| `GridView` | ⬜ | Deferred — sites_screen stays ListView |
| `ResponsiveRow` | ⬜ | Deferred — no tablet layout yet |
| `Card/ListTile/CircleAvatar` | ⬜ | Deferred — glass Containers kept |

## sherlock-project 0.16.0

| Flag | Status | Where |
|---|---|---|
| `proxy` / `--proxy` | ✅ | `state.proxy_url` → `sherlock(..., proxy=)` + `settings` TextField |
| Wildcard `{?}` hint | ✅ | `home_screen.py` SearchBar placeholder |
| Verbose timing sort | ⬜ | `query_time` stored, not yet sortable |
| `--browse` / `--dump-response` | ⬜ | Skipped — low ROI |
| `--tor` | ⬜ | Skipped — needs Orbot, deprecated |

## holehe 1.61

| Capability | Status | Where |
|---|---|---|
| Method filter | ✅ | `results_screen.py` 4 chips (All/Register/Login/Recovery) |
| `frequent_rate_limit` badge | ✅ | `result_card.py` warning text |
| Recovery subtitles | ✅ | `result_card.py` email_recovery/phone already surfaced |
| Concurrency slider | ✅ | `settings` Slider 5–30 → `EmailService.search(concurrency=)` |
| `only-used` | ✅ | `settings` Switch → results filter |
| Batch emails | ⬜ | Skipped — uncommon |
| Categories | ⬜ | Skipped — flat list kept |
| `check_update` | ⬜ | Skipped — mobile no pip |

## socid-extractor 0.1.1 (164 schemes, 449 fields)

| Capability | Status | Where |
|---|---|---|
| Selective mutations | ✅ | `main.py` Basic/Full → `batch_enrich(use_mutations=)` |
| Enrichment mode toggle | ✅ | `settings` Dropdown Basic/Full |
| Dropped fields (company, verified, links) | ✅ | `result_card.py` company/verified/links |
| Relevance pre-filter (`check_url_relevance`) | ⬜ | Deferred |
| Cookie/headers forwarding | ⬜ | Deferred — needs storage plumbing |
| Plugin system | ⬜ | Deferred — community feature |
| `httpx` async path | ⬜ | Deferred — thread hop kept |

## flet-ads 0.86.5

| Capability | Status | Where |
|---|---|---|
| `NativeAd` | ⬜ | User requested skip — not wired |
| Frequency capping (180s / every 3rd) | ✅ | `ad_service.py` `_last_interstitial_ts` + `_search_count` |
| `AdRequest` targeting` | ⬜ | Deferred |
| Debug geography | ⬜ | Deferred |
| Rewarded/AppOpen | ⬜ | Not in 0.86.5 — needs upgrade to 0.87+ |

## Transitives (49 packages)

| Package | Utilization |
|---|---|
| `beautifulsoup4`/`soupsieve` | Via socid — no extra manifest validator yet |
| `httpx` 0.28.1 | Email service uses httpx; enrich still thread-hops requests |
| `python-dateutil` | Via socid NormalizeDates |
| `pandas`/`openpyxl` | Export xlsx kept |
| `stem` 1.8.1 | Pinned for wheel compliance |
