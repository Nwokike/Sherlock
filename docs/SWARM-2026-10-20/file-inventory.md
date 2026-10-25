# Sherlock V3 — Complete File Inventory (2026-10-20)

19,298 lines of Python across `src/` + `tests/` (excluding `__pycache__`).

## src/ (48 Python files)
| # | File | Lines | Role |
|---|---|---|---|
| 1 | src/__init__.py | 0 | package marker |
| 2 | src/app_shell.py | 941 | app shell / routing |
| 3 | src/components/active_scan_banner.py | 109 | component |
| 4 | src/components/app_header.py | 252 | component |
| 5 | src/components/banner_ad.py | 134 | flet-ads banner |
| 6 | src/components/empty_state.py | 88 | component |
| 7 | src/components/profile_detail_dialog.py | 1162 | dossier dialog |
| 8 | src/components/result_card.py | 685 | result card |
| 9 | src/components/section_header.py | 24 | component |
| 10 | src/components/stat_card.py | 64 | component |
| 11 | src/components/targets_card.py | 112 | component |
| 12 | src/components/update_dialog.py | 246 | update flow |
| 13 | src/core/actions.py | 29 | core |
| 14 | src/core/changelog.py | 39 | core |
| 15 | src/core/constants.py | 106 | core constants |
| 16 | src/core/enrich_view.py | 149 | enrichment view model |
| 17 | src/core/format.py | 102 | formatting |
| 18 | src/core/geo_utils.py | 205 | geolocation helpers |
| 19 | src/core/logger_handler.py | 152 | logging |
| 20 | src/core/notify.py | 52 | notification bus |
| 21 | src/core/permute.py | 51 | permutation UI |
| 22 | src/core/shared_services.py | 99 | singletons |
| 23 | src/core/state.py | 240 | scan state |
| 24 | src/core/tasks.py | 31 | task helpers |
| 25 | src/core/theme.py | 339 | theme |
| 26 | src/core/tokens.py | 156 | design tokens |
| 27 | src/hooks/use_debounce.py | 41 | hook |
| 28 | src/main.py | 2452 | entry point |
| 29 | src/screens/history_screen.py | 475 | screen |
| 30 | src/screens/home_screen.py | 1494 | screen |
| 31 | src/screens/onboarding_screen.py | 286 | screen |
| 32 | src/screens/results_screen.py | 1035 | screen |
| 33 | src/screens/settings_screen.py | 1811 | screen |
| 34 | src/screens/sites_screen.py | 784 | screen |
| 35 | src/services/ad_service.py | 323 | flet-ads lifecycle |
| 36 | src/services/cache_service.py | 732 | cache |
| 37 | src/services/email_service.py | 445 | email scan service |
| 38 | src/services/enrich_service.py | 33 | enrichment service |
| 39 | src/services/http_client.py | 112 | shared httpx client |
| 40 | src/services/phone_service.py | 256 | phonsint phone service |
| 41 | src/services/report_service.py | 865 | export service (**broken by dep removal**) |
| 42 | src/services/scan_notify.py | 650 | scan notifications |
| 43 | src/services/sherlock_service.py | 367 | username scan service |
| 44 | src/services/storage_service.py | 367 | persistence |
| 45 | src/services/update_service.py | 119 | app update |
| 46 | src/services/user_scanner_compat.py | 552 | user-scanner adapter |
| 47 | src/state/app_state.py | 9 | state |
| 48 | src/state/controller_ctx.py | 86 | controller context |

## src/assets
`src/assets/fonts/Outfit-Variable.ttf`, `src/assets/icon.png`, `src/assets/icon.svg`

## tests/ (9 files)
| File | Lines |
|---|---|
| tests/conftest.py | 6 |
| tests/test_compat_loader.py | 51 |
| tests/test_cross_scan.py | 67 |
| tests/test_imports.py | 33 |
| tests/test_phone_mode_parity.py | 62 |
| tests/test_services.py | 48 |
| tests/test_services_all_modes.py | 72 |
| tests/test_sites_catalog.py | 39 |
| tests/test_storage_resilience.py | 59 |

## Root config files
`pyproject.toml`, `uv.lock`, `version.json`, `.python-version`,
`.gitignore`, `README.md` (empty), `docs/` (this tree).

## Direct third-party imports used by app code (census)
| Module | Files | Notes |
|---|---|---|
| `flet` | 61 | whole UI |
| `user_scanner.core.*` | 18 | helpers, result, cross_scan, pivots, confidence |
| `phonsint.core.*` | 5+ | phone_service (helpers, parser…) |
| `httpx` | 3 | src/services/http_client.py only |
| everything else | 0 | openpyxl… none — see dependency agent reports |
