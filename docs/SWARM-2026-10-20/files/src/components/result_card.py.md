# Audit: src/components/result_card.py

## 1) File role
`ResultCard` (line 103) is a factory returning a single `ft.Container` row used by both username and email/phone modes. It renders status icon/chip, avatar, title, URL, recovery/phone hints, dynamic enrichment rows (`core/enrich_view`), styled profile fields (bio/location/followers/company/verified/links), method badge, rate-limit/error notices, and the site-country badge. Consumed only by `src/screens/results_screen.py` (`_make_email_card` ~518, `_make_username_card` ~716).

## 2) API verification (flet 1.0.4)
All controls/fields/enums used in this file exist in the installed flet 1.0.4 source (verified: `ft.Alignment`, `ft.Border`, `ft.BorderSide`, `ft.Padding`, `ft.BoxFit`, `ft.TextOverflow`, `ft.CrossAxisAlignment`, `ft.MainAxisAlignment`, `ft.FontWeight`, `ft.Text(no_wrap, max_lines, overflow)`, `ft.Image(src, error_content, fit, border_radius)`, `ft.Container(ink, on_click)`). `ft.Padding(left, top, right, bottom)` positional order matches the field order. No hallucinated API usage found. `ft.use_memo`/`ft.memo` are intentionally NOT used here; memoization lives in `results_screen.py`.

## 3) Engine contract check
- Username mode reads `site_name, status, url_user, url_main, query_time, tags, error_type, error_hint, protection, badge, keyword_hit` from `SiteResult` (`src/services/sherlock_service.py:29-44`); all fields exist. `enrichment` comes from `state.enrichments`, not `SiteResult.ids_data`.
- Email/phone mode reads `name, domain, method, exists, rateLimit, unavailable, frequent_rate_limit, emailrecovery, phoneNumber, others` via the `_to_dict` mapping in `results_screen.py:446-471`; all present in `EmailResult`/`PhoneResult`.
- Service status mapping: username `Status.TAKEN→Claimed`, `AVAILABLE→Available`, `SKIPPED→Skipped`, `ERROR→WAF (bot) / Error` (`sherlock_service.py:308-317`); email `TAKEN→Claimed`, `AVAILABLE→Available`, else `Error/Unavailable` (`email_service.py:142-159`). Engine `Status.to_label()` (`user_scanner/.../result.py:74-81`) produces `Found/Not Found/Error/Skipped` (username) or `Registered/Not Registered/...` (email), but services remap to the card's vocabulary, so the card's labels are consistent with services. `Illegal` is never emitted by services (dead branch at `result_card.py:65`), and `Skipped` is emitted (`sherlock_service.py:316`) but `_status_icon_and_color` (`:61-75`) has no case for it → falls to the error icon/color.

## 4) Parameter census (live/dead)
All 20+ parameters are passed by at least one caller branch, so none is fully dead at signature level. Effectively dead: `tags` (line 120/564) because `get_site_country` always returns `None` without pycountry (see §6). Branch-only parameters:
- Email/phone only: `email_recovery, phone_number, others, method, rate_limit, frequent_rate_limit`.
- Username only: `query_time, enrichment, tags, error_type, error_hint, protection, badge, keyword_hit`.

## 5) Performance findings
- Memoization is at list level in `results_screen.py` (`use_memo` on `_build_result_list`), not per-card; progress ticks that don't change membership skip rebuilds. This file contributes per-card cost only when a list rebuilds.
- Heavy on render path: `enrichment_rows` flattening (`:269-275`), `resolve_location` (`:333`), `get_site_country` (`:564`), string building, and in-function imports (`:269`, `:515`). `resolve_location`/`get_site_country` are `lru_cache`d and no-op without pycountry, so cheap but pointless.
- `_build_result_list` instantiates every card up front even though it uses `build_controls_on_demand` (results_screen), so per-card cost scales with N.

## 6) Bugs (severity-ordered)
1. **High — media fields dropped (except avatar).** At `:216-221` only `v2_media.get("avatar"/"thumbnail_url")` is consumed; at `:269-275` `enrichment_rows` is called with `enrichment` and `v2_extra` only, never `v2_media`; `_merged_profile` (`:305-308`) merges only `v2_extra` and `enrichment`. Confirms the sibling finding: all media fields except the avatar are dropped. Fix: merge `v2_media` into the enrichment/extras source passed to `enrichment_rows` and `_merged_profile`.
2. **Medium — dynamic rows only in email/phone branch.** The `enrichment_rows` block (`:209-300`) is nested inside `if others and isinstance(others, dict)`, so username-mode cards (which pass `enrichment` but no `others`) never render generic socid fields as dynamic rows — only the styled fields (`:309-429`).
3. **Medium — dead geo path.** `:20` imports `core.geo_utils`; `:333-336` `resolve_location` and `:564-572` `get_site_country` always return `None` because pycountry is not installed (verified `ModuleNotFoundError`). The site-country badge never renders and the location never gets a flag.
4. **Low — `Skipped` status unstyled.** `:61-75` has no `Skipped` case, so skipped accounts get the error icon/color.
5. **Low — `Illegal` branch is dead.** `:65` handles a status services never emit.
6. **Low — `links[0]` indexing assumes a non-empty list** (`:417`); guarded by `links and isinstance(links, list) and links[0]`, so safe but silently skips tuples.

## 7) Improvements
- Include `v2_media` in both `_merged_profile` and the `enrichment_rows` call (merge media first, then extras/enrichment so avatar stays reserved).
- Render dynamic rows in the username branch too, or document that username cards intentionally show only styled fields.
- Remove the geo_utils import and the site-country badge (or make pycountry an optional dependency with a visible fallback), since the badge never renders.
- Add a `Skipped` case to `_status_icon_and_color` (neutral icon/color).
- Hoist the in-function imports (`core.enrich_view`, `services.cache_service`) to module top.
- Consider capping work further by computing `_merged_profile`/rows only when `others` or `enrichment` is present (already mostly the case).

## 8) Verdict
The file's flet API usage is correct and its parameter surface is fully wired by callers. The main defect is data loss: media fields (beyond the avatar) are dropped because `v2_media` is never fed to `enrichment_rows`/`_merged_profile`. A secondary issue is a dead geographic path (pycountry absent) that makes the site-country badge and location flags no-ops. Performance is acceptable thanks to screen-level memoization, but per-card flattening and up-front card instantiation in `results_screen` still cost O(N). No crash-level bug found in this file.
