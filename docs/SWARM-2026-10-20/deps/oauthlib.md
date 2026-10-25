# Dependency Audit: oauthlib

**Verdict: N/A — no app opportunity.** Purely transitive, unused, and actively stripped from builds.

## 1) Installed verification

- Version **4.0.0** — `oauthlib/__init__.py:15` (`__version__ = '4.0.0'`); dist-info dir `oauthlib-4.0.0.dist-info`.
- **Sans-I/O confirmed.** `grep -rn "socket" --include=*.py oauthlib/` returns **0** hits — no socket, no HTTP client, no network I/O at all.
  - Only stdlib use is `urllib.parse` for pure string manipulation (`oauthlib/common.py:13-14`, `oauthlib/oauth2/rfc6749/tokens.py:14`, `oauthlib/oauth2/rfc6749/parameters.py:12`).
  - The single `urllib.request` import (`oauthlib/oauth1/rfc5849/utils.py:8`) is used **only** for `urllib2.parse_keqv_list` / `parse_http_list` (lines 64-72) — header parsing helpers, no network calls.
  - It is a spec-compliant OAuth *request-signing* library, not a transport.
- Transitive path confirmed: `flet-1.0.4.dist-info/METADATA:14` → `Requires-Dist: oauthlib>=3.2.2; platform_system != "Emscripten"`. Note the marker — oauthlib is **not installed at all** on Emscripten/Pyodide targets.

## 2) flet's usage + lazy/eager

- flet touches oauthlib in exactly **one** file, `flet/auth/authorization_service.py`, at lines **93, 120, 208** — every one a *function-local* `from oauthlib.oauth2 import WebApplicationClient` (only `WebApplicationClient` is used; the whole oauth1/openid surface is dead weight for flet).
- **Lazy, not eager.** Three independent layers of laziness:
  1. `flet/controls/page.py:69-80` — `_default_authorization_impl()` defers `from flet.auth.authorization_service import AuthorizationService`; its docstring states: *"Deferring these imports keeps the auth subsystem out of the cold-start import graph for apps that never call `Page.login`."* It is invoked **only** inside `Page.login()` (`flet/controls/page.py:1213-1214`).
  2. `flet/auth/__init__.py:32-52` — PEP 562 `__getattr__` resolves `AuthorizationService`, `GitHubOAuthProvider`, `GoogleOAuthProvider`, etc. on first attribute access, not at package import.
  3. `flet/__init__.py` — public API is lazy via PEP 562; only `flet.version` (`flet/version.py:19`, `flet_version = "1.0.4"`) is eager.
- **Cost of eager import: zero at startup for this app.** Since `page.login()` is never called, `flet.auth.authorization_service` is never imported, so `import oauthlib` never happens in a running Sherlock process.

## 3) App usage (zero) + cleanup policy implication

- `grep -rn "oauthlib" --include=*.py src/ tests/` → **0 hits** (confirmed across `src/` and all of `tests/`, incl. `test_imports.py`).
- `grep -rn "Page.login|page.login|\.authorize\(|GitHubOAuthProvider|flet.auth|GoogleOAuthProvider"` across `src/` and `tests/` → **0 hits**. The app uses **no flet auth provider at all**.
- The only `login` strings in `src/` are unrelated target-profile fields: `src/components/profile_detail_dialog.py:78`, `src/components/result_card.py:8` (docstring), `src/services/report_service.py:429,514` — scraped-site bio/username keys, not OAuth.
- **Build policy implication** — `pyproject.toml:55-66`:
  ```toml
  [tool.flet.cleanup]
  package_files = [
      "pycountry/locales/**/LC_MESSAGES/*.mo",
      "pycountry/locales/**/*.po",
      "oauthlib/**",      # <- line 59
      "flask/**", "werkzeug/**", "click/**", "blinker/**", "itsdangerous/**", "asgiref/**",
  ]
  ```
  The owner has explicitly declared oauthlib (and the whole Flask/ASGI server stack) as **strippable from mobile builds** under a build-size policy. Any app code depending on oauthlib would be **actively broken in release builds** (the package is deleted from the APK/IPA payload). Combined with the fact that the app has zero OAuth surface, building on oauthlib would be pointless *and* self-defeating.
- The cleanup entry is **safe**: flet only reaches oauthlib through `page.login()` → `AuthorizationService` → `WebApplicationClient` (all lazy, per §2), and that path is unreachable in this app. Nothing else in flet imports oauthlib.

## 4) Verdict

**N/A — no app opportunity.**

oauthlib is (a) never imported by Sherlock-V3, (b) never used by any flet code path the app exercises, (c) sans-I/O with no transport of its own, (d) declared in `[tool.flet.cleanup]` for removal from mobile builds, and (e) already absent on Emscripten builds. Sherlock-V3 is a username/OSINT scanner with no user-account or third-party-login workflow, so there is no feature that would justify OAuth request signing. The dependency is pure transitive weight from flet's optional auth subsystem and should be left alone — no code changes, no pyproject changes.
