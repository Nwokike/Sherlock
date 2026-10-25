# Audit — `src/components/profile_detail_dialog.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/components/profile_detail_dialog.py` (1,162 lines)  
**Truth sources:** `.venv/lib/python3.14/site-packages/flet` (flet 1.0.4), `.venv/lib/python3.14/site-packages/user_scanner` (user-scanner 1.5.2.3), `pyproject.toml`, `src/services/sherlock_service.py`, `src/screens/results_screen.py`, `src/core/geo_utils.py`, `src/core/enrich_view.py`, `src/core/format.py`, `src/core/actions.py`, `src/core/shared_services.py`  
**Method:** Every control, field, enum, client action, and imported utility was verified against the installed packages in the Python 3.14 venv; contracts between `user_scanner.core.result.Result`, `SiteResult`, and the dossier builders were traced end-to-end.

---

## 1) File role

`src/components/profile_detail_dialog.py` is the application's central modal inspector for OSINT intelligence results. It renders detailed dossiers when users tap result cards in the results screen, supporting two primary operational modalities:
1. **Username Intelligence Dossier (`_username_dossier`):** Surfaces identity cards, avatar images, bio text, audience metrics (followers/following/posts), location, UID, registration date, extracted cross-platform pivot handles, dynamic enrichment key-value pairs, and a collapsible raw OSINT indicator/JSON view.
2. **Email / Phone Intelligence Dossier (`_email_dossier`):** Surfaces account status indicators, probe response times, detection vector/endpoint hints, masked recovery emails, phone hints, and platform links.

### Symbol Breakdown

| Symbol | Line | Role |
|---|---|---|
| `_stringify(value)` | `:22-48` | Fallback text serializer handling non-string extractor objects (lists of dicts, links) |
| `_extract_pivot_handles(enrich, others)` | `:50-94` | Regex & key extractor finding up to 3 cross-platform handles (`@mention`, `*_username`) for search pivoting |
| `_dossier_row(...)` | `:96-163` | Standardized row widget with leading icon, title, value, copy button, and optional external URL action |
| `_open_value(page, url)` | `:165-175` | Async fallback launcher invoking `shared_url_launcher` |
| `_copy_text(page, text, label)` | `:177-188` | Async clipboard helper setting text via `shared_clipboard` and showing snackbar |
| `_email_dossier(...)` | `:190-470` | Builds and displays the `ft.AlertDialog` for email/recovery inspection |
| `_username_dossier(...)` | `:472-1092` | Builds and displays the `ft.AlertDialog` for username OSINT profiles |
| `show_profile_detail_dialog(...)` | `:1094-1163` | Public entry point dispatching to `_email_dossier` or `_username_dossier` with top-level error trapping |

### Consumers (Call Sites)

- `src/screens/results_screen.py:391`: Called from `_show_profile_details(r)` on username search results.
- `src/screens/results_screen.py:417`: Called from `_show_email_details(r)` on email and phone search results.

---

## 2) API verification (Flet 1.0.4)

Every control, argument, and method was checked against installed `flet` 1.0.4 in `.venv/lib/python3.14/site-packages/flet`.

| Usage in file | Installed truth | Verdict |
|---|---|---|
| `ft.AlertDialog(modal=False, title=..., content=..., actions=..., actions_alignment=...)` `:411-468, :994-1090` | `flet/controls/material/alert_dialog.py`: Valid. Inherits from `DialogControl`. `actions_alignment` accepts `ft.MainAxisAlignment`. | **Correct.** |
| `page.show_dialog(dlg)` `:469, :1091` | `flet/controls/page.py:906`: `show_dialog(self, dialog: DialogControl)`. Wraps `on_dismiss`, appends to `_dialogs`, and triggers `_dialogs.update()`. | **Correct.** |
| `page.pop_dialog()` `:213, :409, :460, :497, :970, :1062, :1082` | `flet/controls/page.py:930`: Finds topmost `open=True` dialog in `_dialogs`, sets `open=False`, and calls `update()`. | **Correct runtime API**, but see **B10** for lifecycle race on URL launch failures. |
| `ft.ListView(controls=..., spacing=..., height=300, padding=0)` `:432-437, :1011-1049` | `flet/controls/core/list_view.py`: `ListView(LayoutControl, ScrollableControl)`. All properties valid. | **Correct.** Setting explicit `height=300` avoids flex layout traps inside the dialog. |
| `ft.ExpansionTile(title=..., leading=..., controls=...)` `:929-966` | `flet/controls/material/expansion_tile.py`: Real control in Flet 1.0.4. | **Correct control**, but eager payload dumps inside cause memory/performance issues (see **B14**). |
| `ft.Image(src=..., width=56, height=56, border_radius=28, fit=ft.BoxFit.COVER, error_content=...)` `:562-578` | `flet/controls/core/image.py`: `error_content: Optional[Control]` is supported in 1.0.4. | **Correct Flet API**, but see **B8** for desynced caching behavior. |
| `ft.FilledButton(content=..., icon=..., action=..., on_click=...)` `:453-464, :1073-1086` | `flet/controls/material/filled_button.py` inherits `Button` -> `ActionControl`. `action` takes `ClientAction`. | **Correct.** Flet executes client action on Flutter client before dispatching click event. |
| `ft.OpenUrl(url)` via `core.actions.open_url_action` `:228, :511` | `flet/controls/services/url_launcher.py`: `OpenUrl(ClientAction)` binds to `context.page`. Returns `None` if outside live page context. | **Correct.** |
| `ft.Text(..., selectable=True)` `:150, :690, :948` | `flet/controls/core/text.py`: `selectable: Optional[bool] = None`. | **Correct.** |
| `ft.SelectionArea` | Missing in file. | **Architectural Gap (I1):** Flutter/Flet recommends wrapping dialog contents in `ft.SelectionArea` so text across distinct rows can be selected continuously rather than islanded per-Text control. |
| Icons (`OPEN_IN_NEW_ROUNDED`, `CONTENT_COPY_ROUNDED`, `PERSON_SEARCH_ROUNDED`, etc.) | Verified: all 23 icons referenced exist in `ft.Icons`. | **Correct — zero hallucinated icons.** |
| Enums (`CrossAxisAlignment.CENTER`, `MainAxisAlignment.END`, `BoxFit.COVER`, `ScrollMode.AUTO`, etc.) | Verified: all 6 enums and members exist in Flet 1.0.4. | **Correct.** |

---

## 3) Engine contract

### 3.1 `user_scanner.core.result.Result` and `SiteResult`
The upstream engine `user-scanner` (`user_scanner.core.result.Result`) defines:
- `status`: `Status` enum (`TAKEN`, `AVAILABLE`, `ERROR`, `SKIPPED`)
- `reason`: `str | Exception | None`
- `username`: `str | None`
- `site_name`: `str | None`
- `url`: `str`
- `extra`: `dict[str, str | bool | int]`
- `media`: `dict[str, str]` (avatars, profile pictures, banners)
- `is_email`: `bool`

In Sherlock-V3, `services/sherlock_service.py:341` converts these results into `SiteResult`:
```python
ids_data = {"extra": extra, "media": media} if (extra or media) else None
```

### 3.2 Contract Violations in `profile_detail_dialog.py`

1. **`media` is completely ignored and dropped (B3):**  
   Neither `_username_dossier` nor `core/enrich_view.py` ever inspects `others.get("media")` or `media`. Avatar discovery in `_username_dossier:518` only inspects `enrich.get("image")`, `avatar`, and `photo`. Any media URL returned natively by `user_scanner` in `Result.media` is discarded.
2. **Caller disconnect (`results_screen.py:391` does not pass `others`):**  
   In `results_screen.py:391-402`, `show_profile_detail_dialog` is invoked for username results without passing `others=r.ids_data`. As a result, `others` defaults to `{}`. All `extra` and `media` metadata extracted by `user_scanner` during search is invisible in the dossier modal.
3. **`specially_rendered` suppresses fields that are never rendered (B2):**  
   `:861-863` adds `"company"`, `"occupation"`, and `"is_verified"` to `specially_rendered` under the assumption they were rendered in the upper block. They are never rendered above. Because `enrichment_rows(..., skip=specially_rendered)` skips them, verified badges, company names, and occupations are permanently hidden.
4. **Holehe data dropped in `_email_dossier` (B4):**  
   Holehe returns rich metadata in `others` (e.g. `country`, `language`, `gender`, `about`, `avatar`). `_email_dossier` hardcodes checks for only two keys (`FullName` at `:354` and `Date, time of the creation` at `:364`), discarding all other fields. It never delegates to `enrichment_rows`.
5. **Phone search mislabeled as email (B5):**  
   In `results_screen.py:423`, phone results are dispatched with `mode="email"`. `_email_dossier` displays `"Email Intelligence Dossier"` (`:414`) and `"Investigated Email"` (`:320`) for telephone numbers.

---

## 4) Performance

1. **Per-Open Dialog Tree Rebuild:**  
   The dialog is constructed entirely from scratch on every tap. For an account with 30 enrichment fields, ~200 Flet Control objects are instantiated, serialized to JSON over the protocol, and rendered.
2. **Eager 20,000 Character JSON Formatting (`:925-965`):**  
   Even though the "Raw OSINT Indicators / JSON" drawer is collapsed by default inside `ft.ExpansionTile`, `json.dumps()` is run synchronously on the UI thread during dialog construction, and a 20KB `ft.Text` widget is mounted. This introduces noticeable UI jank on low-end Android hardware.
3. **Double Network Fetch on Avatar Miss (`:562-581`):**  
   When an avatar is not yet cached on disk:
   - `ft.Image(src=avatar_url)` instructs the Flutter client engine to download the image.
   - Concurrently, `spawn(schedule_avatar_download(avatar_url))` launches a Python HTTP streaming task to download the same image.
   Both engines download the image simultaneously, consuming double mobile data.
4. **No True List Virtualization:**  
   `ListView(controls=items)` receives eager Python control instances. While Flutter virtualizes the layout, Python retains every control object in memory.

---

## 5) Bugs (Severity-Ordered)

### High Severity

#### B1: Falsiness bug hides metric strip when counts are zero
- **Location:** `src/components/profile_detail_dialog.py:529-531`, `:705`, `:726`, `:747`
- **Description:**  
  ```python
  followers = enrich.get("follower_count") or enrich.get("followers")
  following = enrich.get("following_count") or enrich.get("following")
  posts = enrich.get("posts_count") or enrich.get("posts")
  ```
  In Python, `0 or None` evaluates to `None`. When an account has `0` followers, `0` following, or `0` posts, the `or` chain evaluates to `None`. The downstream checks `if followers is not None:` evaluate to `False`. Accounts with zero followers or zero posts have their metrics completely hidden instead of displaying "0".
  Similarly, at line `:785`: `if uid:` evaluates to `False` if `uid` is integer `0`.

#### B2: `specially_rendered` permanently suppresses `company`, `occupation`, and `is_verified`
- **Location:** `src/components/profile_detail_dialog.py:861-863`
- **Description:**  
  Keys `"company"`, `"occupation"`, and `"is_verified"` are placed in `specially_rendered` under the comment `# Rendered as the metric strip / identity block above, so they must not also appear as generic rows below`. However, there is no code in `_username_dossier` rendering these fields. Because they are passed to `skip=specially_rendered` in `enrichment_rows()`, they are completely dropped and never shown to the user.

#### B3: `Result.media` from `user_scanner` is dropped completely
- **Location:** `src/components/profile_detail_dialog.py:70, :518, :869`
- **Description:**  
  `user_scanner` populates `Result.media` (containing discovered avatar and banner image URLs), which `sherlock_service.py:341` stores in `ids_data["media"]`. `profile_detail_dialog.py` only ever queries `others.get("extra")`. Discovered media URLs are never rendered, nor are they used as fallback avatar sources.

---

### Medium Severity

#### B4: `_email_dossier` drops all Holehe OSINT fields except `FullName` and `Date`
- **Location:** `src/components/profile_detail_dialog.py:354-372`
- **Description:**  
  `_email_dossier` only checks `others.get("FullName")` and `others.get("Date, time of the creation")`. Rich recovery indicators returned by Holehe (country, language, gender, bio/about, profile URLs) are ignored. Unlike `_username_dossier`, `_email_dossier` never calls `enrichment_rows` and has no catch-all section.

#### B5: Phone search mode displays "Email Intelligence Dossier"
- **Location:** `src/components/profile_detail_dialog.py:320, :414`
- **Description:**  
  When phone number searches are inspected, the screen delegates to `_email_dossier`. The modal title displays `"Email Intelligence Dossier"` and the queried phone number is labeled `"Investigated Email"`.

#### B6: 100% Dead code: `resolve_location` and missing `pycountry` dependency
- **Location:** `src/components/profile_detail_dialog.py:15, :780-781`
- **Description:**  
  The module imports `from core.geo_utils import resolve_location` at top level and calls it at `:780`. `pycountry` is not declared in `pyproject.toml` and is not installed in `.venv`. Every import logs `pycountry library not available` and `resolve_location` returns `None`. The country flag branch at `:781` is completely dead.

#### B7: Unsafe URL synthesis creates invalid URLs containing spaces
- **Location:** `src/components/profile_detail_dialog.py:205-207, :488-490, :209, :493`
- **Description:**  
  Fallback URLs are built via `f"https://{site_name.lower()}.com"`. If `site_name` contains spaces (e.g. `"Hacker News"`, `"Buy Me a Coffee"`), this produces `https://hacker news.com`. Passing unencoded spaces to `url_launcher` causes a `FormatException` in Flutter's `Uri.parse`. Furthermore, checking `startswith("http")` matches domain names starting with "http" (e.g. `httppool.com`), preventing the necessary `https://` prefix from being added.

#### B8: Disconnected avatar caching causes double downloads and static UI
- **Location:** `src/components/profile_detail_dialog.py:562-581`
- **Description:**  
  When an avatar is not cached, `ft.Image(src=avatar_url)` causes Flutter to download the image. Simultaneously, `spawn(schedule_avatar_download(avatar_url))` downloads the image via Python. When Python finishes caching the file to disk, `avatar_control.src` is never updated. The active dialog never benefits from the cached file; only a subsequent dialog open reads from disk.

#### B9: Unhandled `ValueError` in `human_date` can crash modal build
- **Location:** `src/components/profile_detail_dialog.py:804`
- **Description:**  
  `:804` invokes `human_date(raw_date)`. In `core/format.py:63-64`, `text.isdigit()` returns `True` for unicode digits (superscripts like `"²⁰¹⁹"`), causing `int(text)` to raise `ValueError`. Because this call is not wrapped in `try...except`, the exception bubbles to the top-level handler at `:1150`, crashing modal construction and showing a generic error snackbar.

#### B10: Premature `pop_dialog()` on URL launcher failure
- **Location:** `src/components/profile_detail_dialog.py:213, :497`
- **Description:**  
  In `_launch_platform_url` and `_launch_profile_url`, `page.pop_dialog()` is executed before `await shared_url_launcher(page).launch_url(...)`. If the launch fails (e.g. no browser installed or invalid URL scheme), the dialog is already destroyed. The user cannot copy the link without reopening the dialog.

---

### Low Severity

#### B11: Up to 6 action buttons overflow on mobile screens
- **Location:** `src/components/profile_detail_dialog.py:1058-1088`
- **Description:**  
  With 3 pivot buttons, a copy button, a primary open button, and a close button, `AlertDialog.actions` contains 6 buttons. On standard mobile screens (360-400dp width), horizontal overflow forces buttons into a tall vertical stack, encroaching on the 420dp dialog body and causing vertical layout clipping.

#### B12: Hardcoded 380x420 dimensions overflow compact mobile viewports
- **Location:** `src/components/profile_detail_dialog.py:442-443, :1054-1055`
- **Description:**  
  The dialog content container hardcodes `width=380, height=420`. On 360dp mobile viewports with default 40dp dialog margins, the available width is 320dp. The fixed 380dp container exceeds the screen boundary.

#### B13: `site_name.capitalize()` mangles service names in email dossier
- **Location:** `src/components/profile_detail_dialog.py:273`
- **Description:**  
  `site_name.capitalize()` changes `"GitHub"` to `"Github"`, `"PayPal"` to `"Paypal"`, and `"SoundCloud"` to `"Soundcloud"`. In contrast, `_username_dossier:650` correctly preserves the original casing. If `site_name` is `None`, `:273` raises `AttributeError`.

#### B14: Truncated JSON expansion string creates invalid JSON
- **Location:** `src/components/profile_detail_dialog.py:926-927`
- **Description:**  
  `json_str[:20_000] + "\n… (truncated)"` cuts JSON arbitrarily in the middle of tokens or strings, producing malformed syntax that cannot be parsed if copied.

#### B15: Duplicate bio rendering when extractor emits `description`
- **Location:** `src/components/profile_detail_dialog.py:526, :838`
- **Description:**  
  Line `:526` checks `enrich.get("bio") or enrich.get("description")`. However, `specially_rendered` at `:838` only lists `"bio"`. If an extractor returns `"description"`, it is rendered once in the bio container and a second time as a generic row in "All Profile Fields".

#### B16: `_stringify` outputs raw Python dict repr
- **Location:** `src/components/profile_detail_dialog.py:47`
- **Description:**  
  If a value is a dict or set, `_stringify` falls back to `str(value)`, displaying Python-specific syntax like `"{'key': 'value'}"` instead of clean user-facing formatting.

---

## 6) Concrete improvements

1. **Fix falsiness checks for zero metrics:**  
   Replace `enrich.get("follower_count") or enrich.get("followers")` with an explicit sentinel:
   ```python
   def _get_metric(d: dict, *keys):
       for k in keys:
           if k in d and d[k] is not None:
               return d[k]
       return None
   followers = _get_metric(enrich, "follower_count", "followers")
   ```
2. **Restore dropped fields (`company`, `occupation`, `is_verified`):**  
   Either render a verified badge beside `display_name` and add company/occupation rows, or remove them from `specially_rendered` so `enrichment_rows` displays them automatically.
3. **Unify `_email_dossier` with `enrichment_rows`:**  
   Allow `_email_dossier` to pass `others` through `enrichment_rows` so all Holehe indicators reach the user.
4. **Support phone mode cleanly:**  
   Check `mode == "phone"` (or infer from phone query) to display `"Phone Intelligence Dossier"` and `"Investigated Phone"`.
5. **Clean up dead `geo_utils` or add `pycountry`:**  
   Either add `pycountry` to `pyproject.toml` dependencies, or replace `resolve_location` with a lightweight offline mapping dictionary for country codes and flags.
6. **Lazy-load raw JSON in `ExpansionTile`:**  
   Generate `json_str` inside an `on_change` callback when the user expands the tile, rather than during dialog construction.
7. **Responsive dialog sizing:**  
   Use `min(380, page.width - 32)` for dialog width and avoid hardcoding fixed 380dp.

---

## 7) Verdict

`src/components/profile_detail_dialog.py` is an ambitious, well-styled component with clean UI aesthetics, solid Flet 1.0.4 control choices, and zero hallucinated Flet widget APIs. However, it suffers from several severe engine-contract discrepancies:
1. It hides legitimate 0-value metrics (followers/posts) due to Python `or` falsiness traps.
2. It permanently drops `company`, `occupation`, and `is_verified` due to a misplaced exclusion set.
3. It completely drops `media` metadata from `user_scanner`.
4. It fails to show most Holehe recovery metadata in email mode.
5. It depends on a dead geo utility whose underlying package is not installed.

Addressing the high-severity contract bugs (B1, B2, B3, B4) will ensure that no OSINT intelligence returned by the backend engines is lost before reaching the user.
