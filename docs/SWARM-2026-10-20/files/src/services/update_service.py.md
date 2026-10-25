# Audit — `src/services/update_service.py`

**File:** `/home/maikel/.zcode/workspace/default/Sherlock-V3/src/services/update_service.py` (119 lines)
**Audited:** 2026-10-22 · read-only (no source file was modified)
**Truth source:** installed `httpx 0.28.1` + `flet 1.0.4` (`.venv\Lib\site-packages`), repo `version.json`, `pyproject.toml` (`requires-python = ">=3.14"`), Python 3.14.7
**Verification method:** static read + **live execution** of the real module against a stubbed `httpx` client (`src/services/http_client.py` monkeypatched) to confirm each behavioural claim, plus `ruff check` on the file.

---

## 1) File role

`UpdateService` is the app's single remote-config reader. It fetches one public GitHub-raw `version.json`, decides whether the remote build is newer than the running build, and returns a **flat `dict`** (not the dataclass) describing either an *update* or an *announcement*.

| Lines | Role |
|---|---|
| `update_service.py:13-19` | Imports `APP_BUILD_NUMBER`, `APP_VERSION`, `GITHUB_RELEASES_URL`, `PLAY_STORE_URL`, `UPDATE_CONFIG_URL` from `core/constants.py`. |
| `update_service.py:24-28` | `_safe_https_url()` — scheme gate (https only) for every URL that will be handed to the OS browser. |
| `update_service.py:31-32` | `_safe_text()` — "is it a `str`?" gate with default. |
| `update_service.py:35-58` | `UpdateInfo` dataclass + `to_dict()` — the payload contract consumed by the UI. |
| `update_service.py:61-65` | `UpdateService` — holds a single `config_url` (constructor-injectable). |
| `update_service.py:67-119` | `check_for_update()` — the one async entry point: fetch → status check → JSON → freshness gate → sanitize → dict. |

**Consumers (cross-file, for contract only):**
- `src/main.py:2296-2310` — startup check; sets `state.update_available` / `state.update_data`, opens the dialog when `mandatory`.
- `src/components/update_dialog.py:69` — manual "Check for Updates" re-check (`src/components/update_dialog.py:145`).
- `src/components/update_dialog.py:86,90,103,117` — consumes `github_url` / `mandatory` and launches `playstore_url` / `github_url`.

**Shape:** the file is **pure data** — it imports **no flet at all** (verified: no `import flet` in the file). All browser launching lives in `src/components/update_dialog.py:34-46`. That separation is correct and worth preserving.

---

## 2) API verification (installed deps only)

### httpx 0.28.1 — **no hallucinated API**

| Claim | Verdict | Evidence |
|---|---|---|
| `await get_client().get(url, timeout=4.0)` — is `timeout` a valid kwarg on `AsyncClient.get`? | **YES** | `.venv/Lib/site-packages/httpx/_client.py:1751-1768` — `get(self, url, *, params, headers, cookies, auth, follow_redirects, timeout: TimeoutTypes \| UseClientDefault = USE_CLIENT_DEFAULT, extensions)` → forwards to `self.request(...)`. |
| `timeout=4.0` (float) semantics | **Overridden, per-op, not wall-clock** | httpx converts `4.0` → `Timeout(connect=4.0, read=4.0, write=4.0, pool=4.0)`. This **replaces** the client's `httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)` (`src/services/http_client.py:54`). Read timeout 15 s→4 s is the intent; pool 5 s→4 s is a harmless side effect. **Caveat:** httpx's read timeout is *per chunk*, so a server dripping 1 byte/3 s keeps the request open indefinitely — `timeout=4.0` is **not** a total deadline. |
| `resp.json()` on malformed body | **Raises `json.JSONDecodeError`** (a `ValueError`) → caught by the blanket `except Exception` at `update_service.py:116` → returns `None`. **Verified live**: body `"{not json"` → `None`, no crash. |
| `resp.status_code != 200` → early `None` | Correct (`update_service.py:75-77`). Note a future 304 (ETag work, Improvement 6) also lands here → already returns `None` correctly. |
| Shared client ownership | **Correct** — `update_service` borrows the pooled client and never closes it. No lifecycle leak, no per-call client churn (this was the P5-1 fix referenced in the comment at `update_service.py:70-71`). |
| Redirect policy | **`follow_redirects=True` on the shared client** (`src/services/http_client.py:68,76`) → the config fetch follows redirects to **any** host, including link-local/internal addresses. Not reachable today (fixed URL) but not restricted. |
| Proxy awareness | **Working as documented** — `get_client()` reads `state.proxy_url` live (`src/services/http_client.py:43`), so the update check honours the user's proxy. |
| Response size limit | **None** — `resp.json()` buffers the whole body; no `Content-Length` check, no streaming cap. |
| SSRF via request target | `config_url` is a **constructor parameter** (`update_service.py:64`) with **no scheme/host validation**. Both current call sites use the default (`src/main.py:518`, `src/components/update_dialog.py:69`), so **there is no live user-input path today**. |

### flet 1.0.4 — **no hallucinated API in the update chain**

- `page.launch_url` **does not exist** in flet 1.0.4 (no `def launch_url` in `controls/page.py` or `controls/base_page.py`). The repo correctly uses `ft.UrlLauncher.launch_url` via `shared_url_launcher(page)` (`src/components/update_dialog.py:37-39` → `src/core/shared_services.py:97-99`), and `UrlLauncher.launch_url` is `async` (`controls/services/url_launcher.py`, `class UrlLauncher(Service)`), so the `await` is correct.
- `page.show_dialog` / `page.pop_dialog` → **exist** (`controls/base_page.py:402` and `:427`).
- `page.run_task` → **exists** (`controls/page.py:929`).
- `ft.PagePlatform.ANDROID`, `ft.Markdown`, `ft.MarkdownExtensionSet.GITHUB_WEB`, `ft.OpenUrl` → **all exist** (`controls/types.py:804`, `controls/core/markdown.py:928` / `:28-58`, `controls/services/url_launcher.py:188`).
- Icons used by the update dialog (`CAMPAIGN_ROUNDED`, `ROCKET_LAUNCH_ROUNDED`, `VERIFIED_ROUNDED`, `SHOP_ROUNDED`, `DOWNLOAD_ROUNDED`, `SYNC_ROUNDED`) → **all exist** (checked with `hasattr(ft.Icons, …)`).
- `update_service.py` itself has **zero flet surface** → no flet risk in this file at all.

### Repo-side constants contract

- `APP_BUILD_NUMBER = 13`, `APP_VERSION = "2.3.0"` (`src/core/constants.py:17-18`); the shipped `version.json` has `"build_number": 13` → **equals** the local build → the gate (strictly greater) correctly yields "no update" for the local file.
- **Repo-name inconsistency:** `UPDATE_CONFIG_URL` → `raw.githubusercontent.com/Nwokike/Sherlock-V2/main/version.json` and the constant fallback → `github.com/Nwokike/Sherlock-V2/releases/latest` (`src/core/constants.py:25-29`), but the shipped `version.json`'s own `github_url` is `github.com/Nwokike/Sherlock/releases/latest` (no `-V2`). Two different repos for one product; if the server ever omits `github_url`, the fallback sends the user to the V2 releases page.

---

## 3) Confirmed known issues (verify/refute)

| # | Claim | Verdict |
|---|---|---|
| K1 | `:72-74` fetches the update config URL via `services/http_client.get_client()` | **CONFIRMED.** `update_service.py:72` `from services.http_client import get_client` (function-local) and `:74` `resp = await get_client().get(self.config_url, timeout=4.0)`. Live-verified the call is made with `{'timeout': 4.0}`. |
| K2 | `:83-87` freshness gate is an integer `build_number` compare with an `isinstance` guard | **CONFIRMED as the *only* comparison — the `version` string is display-only.** `version` is never compared anywhere; it is only truncated (`:97`) and interpolated into the default title (`:94`). **But the guard is NOT robust** — see NEW-3: it rejects `14.0` and `"14"`, silently disabling updates. |
| K3 | `:101` truncates server release notes | **CONFIRMED.** `release_notes=_safe_text(data.get("release_notes"), "")[:10000]` — hard cap, **no truncation marker** (see NEW-8). Title capped at 500 (`:100`), version at 50 (`:97`), same silent-cut issue. |
| K4 | Changelog fallback at `src/core/changelog.py:39` silently shows the newest entry as current when a version key is missing | **CONFIRMED on the update_service side of the contract.** `CHANGELOG.get(version) or next(iter(CHANGELOG.values()), "")` → dict insertion order → the **first** entry (`"2.3.0"`, `changelog.py:6`), i.e. the newest. Today it is benign because `notes_for(APP_VERSION)` is called with `"2.3.0"`, which **is** a key (`changelog.py:6`). The moment `APP_VERSION` is bumped without a new `CHANGELOG` entry, the "You're up to date" dialog (`src/components/update_dialog.py:206`) shows the *previous* release's notes under the heading "✓ Latest version · v2.4.0". The update_service-side of that contract is **inconsistent**: `UpdateInfo.version` falls back to `APP_VERSION` (`update_service.py:97`) while the title fallback uses `''` (`update_service.py:94`) — the two disagree (NEW-9). |
| K5 | "guarded by tests" comment at `changelog.py:3` is false | **CONFIRMED FALSE.** A repo-wide grep (excluding `.venv`) for `changelog`, `notes_for`, `UpdateService`, `check_for_update` returns **hits only under `src/`** — **zero** test files. `update_service.py` likewise has **zero test coverage** (`tests/` contains 9 files, none reference it). |
| K6 | URL is a public GitHub raw file (no auth) | **CONFIRMED.** `src/core/constants.py:25-27` → `https://raw.githubusercontent.com/Nwokike/Sherlock-V2/main/version.json`; no `Authorization` header, no token, no auth anywhere in the request path. |

---

## 4) NEW bugs (severity-ordered)

### NEW-1 · **High** — "no update" and "the check failed" are the *same* return value
`check_for_update()` returns `None` for **five different outcomes**: HTTP ≠ 200 (`:75-77`), non-dict body (`:80-81`), stale build (`:86-87`), any exception (`:116-119`), and "server genuinely has nothing new". The caller cannot tell them apart, so:
- `src/main.py:2300-2309` → `elif notify_if_latest: self._show_snack("Sherlock v2.3.0 is up to date!")` — **a user offline, behind a broken proxy, or served malformed JSON is told they are up to date.**
- `src/components/update_dialog.py:75-78` → same false "up to date!" snackbar from the manual button.
- The header chip (`src/components/app_header.py:42`) never appears, and no error surfaces anywhere.
Live-verified: malformed JSON, non-dict JSON and HTTP 404 all collapse to `None`, identical to a genuine "up to date".

### NEW-2 · **High** — the anti-spam policy in the comment is a no-op; announcements repeat on *every* launch
`update_service.py:84-85` claims gating announcements on `build_number` "prevents remote announcement spam on every launch". It does not:
- The gate only rejects announcements whose build is **≤** the local build. Any announcement published with `build_number > 13` is re-detected **on every single launch**.
- Nothing records that it was seen: `state.update_available` / `state.update_data` are plain in-memory attributes (`src/core/state.py:152-153`), not persisted; the service keeps no last-seen id or content hash.
- Worse: `mandatory: true` on an announcement makes the dialog `modal=True` (`src/components/update_dialog.py:195`) and **suppresses the "Later" button** (`src/components/update_dialog.py:130`) → an **un-dismissable modal on every launch** until the user upgrades past that build. A single bad server-side flag bricks the app's UX.

### NEW-3 · **Medium** — a non-integer `build_number` silently disables all updates
`isinstance(server_build, int)` (`update_service.py:86`) rejects JSON floats and numeric strings. **Live-verified against the real module:**
- `{"build_number": 14.0}` → **`None`** (no update shown)
- `{"build_number": "14"}` → **`None`**
- `{"build_number": true}` → `None` — note `isinstance(True, int)` is **True** in Python, so a JSON boolean *passes* the guard (harmless only because `True <= 13`); the guard is not bool-safe.
A server that publishes `14.0` or quotes the number makes every client report "up to date" **forever**, with the failure visible only at DEBUG level. This is a fail-open-to-stale configuration error.

### NEW-4 · **Medium** — no cooldown, no in-flight lock, no caching: every launch and every button press hits the network
There is no minimum-interval guard, no `asyncio.Lock`, no result cache, and no `ETag`/`If-None-Match`. `check_for_update()` is invoked at startup (`src/main.py:535`) and by the "Check for Updates" button (`src/components/update_dialog.py:69`, wired at `:145`). Consequences: the button can be spammed, each press issues a fresh HTTPS request to `raw.githubusercontent.com`; a startup check plus a manual check can double-fire concurrently; the whole JSON is re-downloaded every time. This service is the natural home for all three controls and implements none.

### NEW-5 · **Medium** — `config_url` is an unvalidated network target (latent SSRF seam)
`update_service.py:64` — `def __init__(self, config_url: str = UPDATE_CONFIG_URL)` accepts **any** string: no scheme check, no host allowlist, no `https` enforcement, and it is used verbatim as the request target at `:74`. There is **no live user-input path today** (both call sites use the default), but the app already has a user-configurable proxy, so any future "custom update server" setting turns this into an SSRF primitive (including `file://`-style confusion and internal-IP probing). The asymmetry is backwards: the **response** URLs are validated by `_safe_https_url` (`:24-28`), while the **request** URL is not.

### NEW-6 · **Medium** — `_safe_https_url` blocks `http:`/`javascript:` but allows **any** https host, so a button can lie about its destination
`_safe_https_url` (`:24-28`) enforces only the `https://` prefix. The server controls `github_url`, `playstore_url` and `action_url` (`:103-107`), and the UI labels those buttons "Download from GitHub" / "Direct APK (GitHub)" / "Google Play" (`src/components/update_dialog.py:92,106,121`) while launching **whatever URL the server supplied**. Anyone able to write to the version.json repo (or win a DNS/redirect trick) can point the "Download from GitHub" button at an arbitrary https host. Verified working as intended for scheme blocking: `http://evil.com` → rejected; `javascript:alert(1)` → rejected.

### NEW-7 · **Low-Medium** — `_safe_https_url` is case-sensitive and does not reject control characters
Live-verified against the real helper:
- `"HTTPS://github.com/x"` → **falls back to the default** — a legitimately cased URL is discarded (the scheme comparison must be case-insensitive per RFC 3986).
- `"https://"` → **accepted verbatim** — a nonsense URL that survives all the way to the platform launcher.
- `"https://ok.com\njavascript:x"` → **accepted verbatim** — CR/LF smuggling into a URL handed to the OS.

### NEW-8 · **Low-Medium** — release-note truncation is silent and can break Markdown rendering
`update_service.py:101` caps at 10 000 chars with no marker. The dialog renders that string as GitHub-flavoured Markdown (`src/components/update_dialog.py:181-186`), so a cut inside a fenced code block or a bold span yields broken rendering, and the user is never told the notes were shortened. Same silent-cut pattern at `:97` (version, 50) and `:100` (title, 500).

### NEW-9 · **Low** — the title fallback disagrees with the version fallback
`:94` builds the default title from `_safe_text(data.get('version'), '')` (empty-string default) while `:97` fills `version` with `APP_VERSION` when the server omits it. **Live-verified**: a body without `version` yields `version == "2.3.0"` but `title == "Version  Available!"` — a double space and no version number. (This is also the update_service-side seam of the changelog contract in K4.)

### NEW-10 · **Low** — `action_url` is a dead output field
Produced at `update_service.py:45`, `:57` and `:107`; a repo-wide grep for `action_url` hits **only** `update_service.py`. `src/components/update_dialog.py` never reads it. Either a half-built feature (an announcement CTA button) or dead payload shipped to every caller.

### NEW-11 · **Low** — the blanket `except Exception` hides import failures and programming errors
`update_service.py:116` catches everything, including the `ImportError`/`SyntaxError` raised by the function-local import at `:72`. If `services.http_client` ever fails to import (e.g. a `requires-python` mismatch — note `src/services/http_client.py:33` and `src/components/update_dialog.py:228` use the PEP 758 `except TypeError, ValueError:` form, which is **Python 3.14+ only**; the repo pins `requires-python = ">=3.14"` in `pyproject.toml`, so it is correct today, but the failure mode would be a *silently dead* update check, not a crash). It also swallows `httpx.InvalidURL` / `TooManyRedirects` and logs at **DEBUG** (`:117`) — invisible in a normal INFO run.
**Credit where due:** `asyncio.CancelledError` is a `BaseException` in Python 3.8+, so `except Exception` does **not** swallow cancellation — the teardown path is correct.
**Note:** `BLE001` is globally ignored (`pyproject.toml:94`), so `ruff check src/services/update_service.py` → **"All checks passed!"**. The blind except is config-blessed, not accidental.

### NEW-12 · **Low** — `version` is display-only and can silently contradict `build_number`
The freshness decision uses **only** `build_number` (`:86`); `version` is never compared (K2). The repo's own `version.json` pairs `build_number: 13` with `version: "2.3.0"` and `APP_BUILD_NUMBER`/`APP_VERSION` agree today (`src/core/constants.py:17-18`), but nothing enforces it. A server that bumps `build_number` without `version` makes the dialog claim "Version 2.3.0 is now available" for a build the user already runs (`src/components/update_dialog.py:177`); a server that bumps `version` without `build_number` is invisible.

### NEW-13 · **Low** — no response-size cap
`resp.json()` (`:79`) buffers the entire body with no `Content-Length` check and no streaming limit. Bounded today by the fixed URL + 4 s timeout, but with `follow_redirects=True` on the shared client a redirect to a large host would stream unboundedly into memory.

### NEW-14 · **Informational** — `mandatory` is strict-typed and only reachable through a build bump
`data.get("mandatory") is True` (`:102`): a server publishing `"mandatory": "true"` (string) or `1` yields **False** → the update silently becomes dismissible (**live-verified**). And because the whole block sits behind the build gate (`:86`), a *mandatory advisory that does not bump `build_number` is never delivered at all* — there is no separate "critical notice" channel.

---

## 5) Improvements (concrete)

1. **Return a status, not `None`** (fixes NEW-1). Replace `dict | None` with a typed result so the caller can distinguish "up to date" from "check failed":
   ```python
   @dataclass
   class UpdateCheckResult:
       status: Literal["update", "up_to_date", "error"]
       info: UpdateInfo | None = None
       error: str | None = None
   ```
   Then `src/main.py:2308` shows "up to date" only for `status == "up_to_date"`, and shows "couldn't reach the update server" for `status == "error"`.
2. **Cooldown + de-duplication** (fixes NEW-4). Keep `self._last_check: float` (monotonic) and an `asyncio.Lock` on the service; add `force: bool = False` so the manual button bypasses the interval. Suggested floor: 30 min between automatic checks, 0 for the manual path.
3. **Persist the cooldown and the seen-announcement marker** (fixes NEW-2). `StorageService` already exposes `async get/set/delete` (`src/services/storage_service.py:284-311`) and `core/constants.py` has the key namespace — add e.g. `STORAGE_UPDATE_LAST_CHECK` and `STORAGE_UPDATE_SEEN_ID`. Store a hash of `title + release_notes + build_number`; skip re-showing an announcement whose id was already seen. That makes the "no spam" comment at `:84-85` actually true.
4. **Coerce `build_number` instead of `isinstance`-rejecting it** (fixes NEW-3):
   ```python
   def _coerce_build(value: object) -> int | None:
       if isinstance(value, bool):
           return None
       if isinstance(value, int):
           return value
       if isinstance(value, float) and value.is_integer():
           return int(value)
       if isinstance(value, str) and value.strip().isdigit():
           return int(value.strip())
       return None
   ```
   Also drops the now-redundant `int(server_build)` at `:98`.
5. **Host-allowlist the launched URLs** (fixes NEW-6). Extend `_safe_https_url` with an allowed-host set (`github.com`, `play.google.com`) and refuse server-supplied URLs outside it — the button labels promise specific hosts.
6. **Conditional GET.** Store the `ETag` in storage and send `headers={"If-None-Match": etag}`; `status_code != 200` at `:75` already treats 304 as "no update", so only the header plumbing is needed. Saves bandwidth on every launch.
7. **Explicit exception taxonomy** (fixes NEW-11). Catch `httpx.TimeoutException`, `httpx.HTTPError` and `json.JSONDecodeError` separately, log at INFO with the exception class, and let anything else propagate as a bug rather than a silent "no update".
8. **Tighten URL hygiene** (fixes NEW-7): compare the scheme case-insensitively (`value.lower().startswith("https://")`), reject control characters/whitespace, and require a non-empty host after the prefix.
9. **Cap the body** (fixes NEW-13): check `Content-Length` and/or read with `client.stream()` under an explicit byte cap; if the shared client keeps `follow_redirects=True`, assert `resp.url.host == "raw.githubusercontent.com"` before parsing.
10. **Mark truncation** (fixes NEW-8): append an ellipsis plus a "read the full notes at <github_url>" line when the 10 000-char cap is hit, so the Markdown cannot silently break.
11. **Make the fallbacks consistent** (fixes NEW-9): use `APP_VERSION` as the default in the title fallback at `:94` too, so `title` and `version` can never disagree.
12. **Accept `1`/`"true"` for `mandatory` but keep bools strict** (fixes NEW-14) and log a WARNING when the server sends a shape the parser had to guess at.
13. **Drop or wire up `action_url`** (fixes NEW-10). Either render it as an announcement CTA button or delete `:45`, `:57`, `:107`.
14. **Add tests — the module has none.** Minimum table: build-number coercion (int / float / numeric string / bool / missing), malformed JSON, non-dict JSON, non-200, https scheme + host allowlist, `mandatory` coercion, announcement de-duplication, cooldown window. A 40-line `pytest` file with a stubbed client (as used for this audit) covers all of it.
15. **Raise the log level of failures** to INFO (`:117`) so support can see a broken update check; keep the happy path at DEBUG.

---

## 6) Verdict

**Structurally sound, API-correct, but semantically lossy.**

- **No hallucinated APIs.** Every httpx and flet call in the update chain exists in the installed versions (`httpx 0.28.1`, `flet 1.0.4`); `page.launch_url` correctly *doesn't* exist in 1.0.4 and the repo uses the right `ft.UrlLauncher` path instead. `update_service.py` imports no flet at all, which is the right separation. `ruff check` passes.
- **The known context is accurate**: the fetch goes through `get_client()` with `timeout=4.0` (`:72-74`); the freshness gate is an integer `build_number` compare and the `version` string is display-only (`:83-87`); release notes are truncated at 10 000 chars (`:101`); the changelog fallback claim and the false "guarded by tests" comment are both confirmed.
- **Two structural weaknesses carry most of the risk.** (a) The `None` return contract collapses *up-to-date*, *stale-remote* and *network-failure* into one value, so the app actively lies to the user when it cannot reach GitHub (NEW-1). (b) The documented "no announcement spam" policy is a no-op — nothing tracks what the user has already seen, and a `mandatory` announcement produces an un-dismissable modal on every launch (NEW-2).
- **Fix order:** NEW-1 (result contract) → NEW-2 (seen-announcement persistence) → NEW-3 (build-number coercion) → NEW-6 (host allowlist) → NEW-4 (cooldown/lock) → NEW-5 (validate `config_url`). Everything else is polish.
- **Test debt is the underlying risk:** the file, and the changelog contract it feeds, have **zero** coverage — which is exactly why the "guarded by tests" comment at `changelog.py:3` can be false without anything going red.
