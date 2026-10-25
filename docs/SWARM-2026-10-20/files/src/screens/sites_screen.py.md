# Audit — `src/screens/sites_screen.py` (784 lines)

Audited against installed deps only: **flet 1.0.4**, **user-scanner 1.5.2.3**, **phonsint 0.1.0** (`.venv/lib/python3.14/site-packages`, CPython 3.14). Scope: this file only.

---

## 1. File role

`SitesScreen` is a `@ft.component` (`:191`) that lets the user include/exclude individual social networks from a scan. It reads `AppStateCtx`/`ControllerMethodsCtx` (`:193-194`), renders a mode pill (Username/Email/Phone) (`:658-672`), a debounced search bar (`SitesSearchBar`, `:144-188`), category chips (`:494-526`), bulk-action buttons (`:534-584`), stats (`:619-638`), and a `ListView` of `SiteRow` checkboxes (`:775-784`). Selection is persisted through `controller.save_selected_sites` (`:264`) with a 300 ms debounce (`_persist_debounced`, `:251-273`). Site names come from `state.sites_cache` (populated by `AppController._load_and_cache_sites`, `main.py:854`), tagged via `state.sites_tag_index`/`sites_tags_map`.

---

## 2. API verification

Most APIs are valid against flet 1.0.4. Findings:

| Line(s) | API / claim | Verdict |
|---|---|---|
| `:739-747` | `_root_list.current.scroll_to(offset=0, duration=250)` inside `build_controls_on_demand=True` ListView | **Dead** — `scrollable_control.py:409-411` documents `scroll_to` ineffective for controls that build items dynamically. Confirmed: with `build_controls_on_demand=True` (`:779`) the call is a no-op. |
| `:640-645` | comment "flet 1.0.4 ignores `expand` on column children … no control sets `host_expanded`" | **False** — `core/column.py:88` sets `self._internals["host_expanded"] = True`. This false belief is the stated reason the header rides inside the ListView (`:640-645`), which in turn is why `scroll_to` is dead. |
| `:779` | `build_controls_on_demand=True` | Valid and necessary for 5k+ rows; but combined with the header inside the list it disables `scroll_to`. |
| `:780` | `cache_extent=2000` (pixels) | Valid (`list_view.py:108-125`). |
| `:75-75` | `_ROW_HEIGHT = 56.0` + `height=_ROW_HEIGHT` on `SiteRow` | Valid, but `item_extent` is deliberately unset (`:752-759`) because header/banners of mixed height break virtualized offsets. |
| `:101-102` | `ft.ValueKey(name)` on Checkbox | Valid. |
| `:118` | Checkbox `on_change=lambda e: on_toggle(name)` | Valid; ignores event payload. |
| `:152` | `use_debounce(raw, 200)` | Valid custom hook (`hooks/use_debounce.py`). |
| `:193-194` | `ft.use_context(AppStateCtx/ControllerMethodsCtx)` | Valid. |
| `:205` | `ft.use_ref(None)` for `_root_list` | Valid. |
| `:219` | `ft.use_effect(lambda: _cleanup_persist, [])` returns cleanup fn | Valid (returns `_cleanup_persist`). |
| `:395-442` | `ft.use_memo(...)` | Valid. |
| `:499-504` | `ft.Chip(on_select=...)` with `selected=` | Valid (`chip.py:252`); mutually exclusive with `on_click`. |
| `:659-667` | `ft.SegmentedButton(selected=[state.search_mode], on_change=...)` | Valid. |
| `:770` | `pooled_banner_ad(...)` | Valid (per known context). |
| `:487-492` | `from core.geo_utils import get_country_by_tag` | API exists, but **dead at runtime** because `_PYCOUNTRY_AVAILABLE` is `False` in this env (`geo_utils.py` guards on `pycountry` import; `pycountry` is not installed). Returns `None` always → `_country_chip_label` falls back to bare code (`:492`). |
| `:450-452` | `_is_country(k)` 2-letter country detection | **Dead path**: `sites_tag_index` keys are category folder names (`social`, `dev`, …), never 2-letter country codes, so `live_countries` is always empty and the country chip row never renders. |

---

## 3. Catalog + selection correctness

- **Row counts**: username 2,521 / email 220 / phone 5 unique site names, matching `user_scanner`/`phonsint` module counts (verified). `state.sites_cache` is `sorted(set(names))` (`sherlock_service.py:119`).
- **Category filtering inconsistency**: `SherlockService.load_sites` (`sherlock_service.py:130-133`) builds `sites_tag_index` as `{cat: [m.__name__.split(".")[-1]]}` (lowercase module basenames), whereas `PhoneService.load_sites` (`phone_service.py:78-82`) uses `get_site_name_phone(m)` (capitalized). The screen lowercases keys but keeps values as-is (`:409`), and `canonical_names` are capitalized (`get_site_name` capitalizes). So for **username/email** modes the bucket values are lowercase basenames while names are capitalized → category chips filter to **zero rows** for those modes; only phone mode filters correctly. (Root cause in service, but visible here: `_compute_filtered` `:415-435`, `bucket` membership `:426`.)
- **Selection init** (`_init_states`, `:221-243`): preserves manual toggles across re-inits; seeds from `state.selected_sites` (empty list == "all selected"). Correct semantics.
- **Stale accumulation bug**: `_init_states` only adds names present in `available`; it never drops entries for names no longer present (`:234-240`). On a mode switch (`_switch_module_mode`, `:646-657`) `checked_states` keeps the previous mode's networks, so `checked`/`total`/`missing` stats and persisted scope leak across modes. Should reset `checked_states` to `{}` before/alongside the reload.
- **Persist debounce** (`_persist_debounced`, `:251-273`): coalesces writes; all-selected stored as `[]` (`:263-266`). Matches `selected_sites` semantics. Race: `_pending_states.current` is a ref shared across renders; rapid mode switches can persist a stale snapshot. Minor.
- **Search filtering**: case-insensitive via `.lower()` (`:416`, `:430`); unicode-aware Python `str.lower`. Tag fallback included (`:431`). Correct.
- **Scope to filter** (`_scope_to_filter`, `:353-380`): includes the live query in the view (`:364-365`); empty match guarded (`:369-371`). Correct.
- **Bulk actions** operate on `filtered_names` (full match set, not just the 120-row window) (`:330-351`). Correct and important.

---

## 4. Performance

- Windowing (`_INITIAL_ROWS=120`, `_ROW_STEP=120`, `:84-86`) caps first paint; extension on scroll at 85% (`_on_scroll`, `:297-313`). Good mitigation.
- `canonical_names`/`lowered_tags`/`tag_buckets` memoized on `sites_version` (`:395-413`); `filtered_names` memoized on query/tag/version (`:439-442`). Toggles do not re-filter (documented `:437-438`). Good.
- `SiteRow` isolated so a toggle re-renders one row (`:89-141`). Good.
- `SitesSearchBar` isolates keystrokes (`:144-188`). Good.
- `build_controls_on_demand=True` + `cache_extent=2000` (`:779-780`). Good.
- Remaining cost: `items` comprehension still builds `SiteRow` for the whole `shown` window on every render (`:478-482`); window grows to thousands as user scrolls, so later renders get expensive. `item_extent` cannot be used while header/banners share the list (`:752-759`).
- `_compute_chips` and `_compute_filtered` iterate all names on their deps; acceptable.

---

## 5. Bugs (severity-ordered)

1. **High — "Jump to top" / Back-to-filters button is dead** (`:567-573`, `_scroll_to_top` `:732-747`). `scroll_to` is documented ineffective on dynamically-built ListViews (`scrollable_control.py:409-411`) and this ListView has `build_controls_on_demand=True` (`:779`). Once scrolled past ~10 rows the search bar and category chips are unreachable. Root cause is the header living inside the ListView (`:640-645`, based on the false expand claim).
2. **High — Mode switch leaks stale selection state** (`_switch_module_mode`, `:646-657`; `_init_states`, `:221-243`). `checked_states` is not cleared, so counts/stats/`missing` and persisted scope carry the previous mode's network names.
3. **Medium — Category filtering broken for username/email modes** (service-side, surfaced in `_compute_filtered` `:415-435`): `sites_tag_index` values are lowercase module basenames for those modes but capitalized site names in `canonical_names`. Phone mode is correct.
4. **Medium — `geo_utils` country badge always bare code** (`_country_chip_label`, `:485-492`) because `pycountry` is not installed; and the country-chip row is effectively dead anyway (`:450-470`, no 2-letter tag keys).
5. **Low — `use_effect(_init_states, [state.sites_version])`** (`:244`) reads `checked_states` from the render closure; effect only re-runs on version bump, so a toggle between loads does not re-seed (intended), but the closure captures the version at which it was registered. Verify ordering if `sites_version` resets to 0 on mode switch then increments.
6. **Low — `items` comprehension rebuilds `SiteRow` for the whole visible window each render** (`:478-482`), including on any state change that re-renders the parent.
7. **Low — `_scroll_to_top` is defined after `bulk_actions` references it** (`:534-584` vs `:732-747`); works only because the lambda resolves the name at click time. Fragile but functional.

---

## 6. Improvements — header-out-of-ListView restructure (concrete sketch)

Move `header_block` (mode pill, search bar, category chips, bulk actions, stats) **out** of the `ListView` into a `Column` (or `SafeArea` + `Column`) that is the screen root, with the `ListView` as the `expand=True` child. Because `column.py:88` sets `host_expanded=True`, `expand` on the ListView child works, so the list gets bounded height and scrolls; the header stays pinned and reachable. This also makes `scroll_to` unnecessary (filters always visible) and, once banners are handled, allows `item_extent=_ROW_HEIGHT` for true virtualization over ~5,178 rows.

Sketch:

```python
# screen root
return ft.Column(
    controls=[
        *header_block,                       # pinned, never scrolls
        ft.ListView(                          # only rows + banners scroll
            controls=controls,                 # rows (+ optional banners)
            spacing=0,
            expand=True,
            build_controls_on_demand=True,
            item_extent=_ROW_HEIGHT,           # now safe: every list item is 56px
            cache_extent=2000,
            on_scroll=_on_scroll,
            key=ft.ValueKey("sites-networks-root"),
        ),
    ],
    spacing=0,
    expand=True,
)
```

Notes for the restructure:
- Remove banners from the virtualized list OR give them a fixed height and keep `item_extent` off; alternatively move ads to a non-virtualized slot above/below the list. Mixed heights defeat `item_extent`.
- Drop `_scroll_to_top` and the "Back to filters" IconButton (`:560-573`) — no longer needed; reclaim horizontal space.
- Reset `checked_states` on mode switch (see bug 2) and clear `_root_list` ref (no longer needed).
- Keep `SitesSearchBar` isolated so keystrokes still don't rebuild rows.
- Verify on device that the `ListView` expands inside the app's `SafeArea` mount (the file's own caveat, `:758-759`); if not, wrap in `ft.Container(expand=True)`.

---

## 7. Verdict

The screen is well-engineered (windowing, memoization, isolated rows/search bar, debounced persistence, scope semantics) and most flet API usage is correct. Two structural defects dominate: the **dead `scroll_to`/unreachable filters** caused by the header riding inside a dynamically-built `ListView` (rooted in a **false belief about `expand` on `Column` children**, `:640-645`), and **cross-mode leakage of `checked_states`**. Category filtering is correct only in phone mode due to a service-side tag-index inconsistency. The recommended fix is the header-out-of-ListView restructure in §6, which restores filter reachability, unlocks `item_extent` virtualization for ~5,178 rows, and lets the dead `scroll_to` button be removed. Geo/country chip code is dead in this environment (pycountry absent and no 2-letter tag keys) and can be trimmed.
