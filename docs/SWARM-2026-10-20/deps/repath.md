# repath 0.9.0 — Dependency Audit (Sherlock-V3)

**Question:** does Sherlock-V3 use `repath`, and could/should it?
**Answer:** No. `repath` is a pure transitive of `flet`, used *only* by flet's `TemplateRoute` and
`Router` components. The app uses **neither** and does **not** import `repath`. Navigation is a
plain `use_state` screen switch — no route table, no URL, no hand-rolled route parser that
`repath` could replace. **No action.**

## 1. Installed verification (venv = source of truth)

`.venv\Lib\site-packages\repath.py` (single 8,205-byte module) + `repath-0.9.0.dist-info\`.

- **Version 0.9.0** — `repath-0.9.0.dist-info\METADATA:3` → `Version: 0.9.0`; `:1` `Name: repath`.
- **Purpose/license** — `METADATA:5` "Generate regular expressions form ExpressJS path patterns"; MIT;
  Nikolaos Coutsos (port of node's `pathToRegexp`). Sdist uploaded 2019-10-08 (`uv.lock:425`).
- **Pulls `six`** — `METADATA:24` `Requires-Dist: six (>=1.9.0)`; installed `six.py` = **1.17.0**
  (unmaintained Py2/3 shim).
- **Public API** — `repath.py`: `escape_string`:64, `escape_group`:72, `parse`:76,
  `tokens_to_template`:134, `tokens_to_pattern`:197, `compile`:239, `match`:252, `pattern`:266,
  `template`:288.
- **Transitive, not declared** — `uv.lock:135`: flet 1.0.4 deps include `{ name = "repath" }`;
  package entry `uv.lock:419-427`. `pyproject.toml:7-12` declares only `flet>=1.0.4`,
  `flet-ads>=1.0.4`, `user-scanner>=1.5.2.3`, `phonsint>=0.1.0` — **no `repath`**.

**Real import test** (`.venv\Scripts\python.exe`, Python 3.14.7, against installed source):
`repath.pattern('/users/:id/posts/:pid')` → `^/users/(?P<id>[^/]+?)/posts/(?P<pid>[^/]+?)(?:/(?=$))?$`;
`re.match(...).groupdict()` → `{'id': '42', 'pid': '7'}`. Works on 3.14.7 despite the 2019 vintage.

## 2. flet usage sites + app routing facts (file:line)

flet **1.0.4** installed (`flet-1.0.4.dist-info`). Exactly two consumers:

- `.venv\Lib\site-packages\flet\controls\template_route.py:3` `import repath` → `:44`
  `pattern = repath.pattern(route_template)`, `:45` `re.match(pattern, self.route)`. Exported as
  `ft.TemplateRoute` (`flet\__init__.py:622, 1179, 1721`).
- `.venv\Lib\site-packages\flet\components\router.py:16` `import repath` → `:191`
  `repath.pattern(full_path)`; `:228`, `:265` `repath.pattern(full_path, end=False)`; `:287`, `:302`
  `repath.pattern(full_path)`. Exported as `ft.Router`/`ft.Route` (`flet\__init__.py:42, 1103, 1645`).

**App facts** (grep of `src/` and `tests/`):

- `repath` — **0 hits** in app code; only `uv.lock:135, 419, 425, 427`.
- `TemplateRoute` — **0 hits**. flet's `Router`/`Route` — **0 hits**.
- `page.go` / `page.route` / `on_route_change` / `route_change` — **0 hits** (near-misses are
  `launch_url(...)` external links: `src\components\profile_detail_dialog.py:169, 217, 501`,
  `src\screens\results_screen.py:353`, `src\components\update_dialog.py:39`).
- Routing is **local state**, not URLs:
  - `src\app_shell.py:707-708` — `active_tab, set_active_tab = ft.use_state(0)`;
    `active_view, set_active_view = ft.use_state("dashboard")`.
  - `src\app_shell.py:725-728` — controller closures set `active_view` to `"results"`/`"sites"`/`"dashboard"`.
  - `src\app_shell.py:732-743` — system back mapped onto in-app state transitions.
  - `src\app_shell.py:909-932` — `ft.use_memo` picks the screen component from `branch` + `active_tab`
    (onboarding / results / sites / home / history / settings).
  - `src\app_shell.py:758-786` — chrome sync mutates `page.views[0].appbar` / `.navigation_bar`.
  - `src\main.py:588` — `self.page.render(lambda: ControllerMethodsCtx(methods, lambda: AppShell()))`
    (single declarative root, no route table); `src\main.py:587` `on_view_pop = _on_system_back`;
    `src\main.py:606-614` operates on `self.page.views[-1]` — **one view**, not a view stack.
    Entry: `src\main.py:2396` `async def main(page)`, `:2452` `ft.run(main, ...)`.
- Closest thing to "path parsing": `src\screens\home_screen.py:345-348` (`urlparse` +
  `.path.split("/")`) normalizes a **user-supplied OSINT target** (`example.com/path` → username),
  not navigation. Not a route matcher.

## 3. Opportunity assessment (honest)

**(a) Is the app hand-rolling route parsing that `repath` could replace? — No.** The app parses *no*
routes. Navigation is a 6-way closed enum carried in a `use_state` string, with zero URL surface,
zero path parameters, zero deep links — nothing hand-rolled for `repath` to improve.
`src\screens\home_screen.py:345-348` is target-input normalization, not routing; `repath` matches
URL paths against templates and would be a semantic mismatch there.

**(b) Does flet's views/`page.go` cover it? — It doesn't need covering; the app uses a single-view
`page.render` + local state, not `page.go`/`page.route`.** The installed flet *does* ship the
alternatives (`flet\controls\page.py:636` `on_route_change`; `flet\components\router.py`
`Router`/`Route`/`use_route_params`). If the app ever needed URL-addressable deep links,
`ft.Router` or `ft.TemplateRoute` would deliver them with **zero new dependencies** (`repath` is
already installed transitively). But there is no requirement today, and the migration cost is real:
introducing a location/URL concept, replacing the controller-closure injection
(`src\app_shell.py:725-754`) and the `use_memo` branch switch (`src\app_shell.py:909-932`), and
reworking system-back (`src\app_shell.py:732-743`, `src\main.py:587`) — while flet's Router brings
view-stack/swipe-back semantics that can conflict with the single-view model. High risk, zero gain.

**If a direct `repath` import were ever contemplated:** it is currently an *undeclared* (transitive)
dependency, so it would have to be added to `pyproject.toml:7-12` to be correct. The right door is
flet's public API (`ft.TemplateRoute` / `ft.Router`), not `import repath` — that keeps the 2019
package and its `six` shim inside flet's problem.

## 4. Verdict

**No action. Leave `repath` as an untouched transitive of `flet`; do not add it to `pyproject.toml`.**

- Installed 0.9.0 via `flet` 1.0.4 (`uv.lock:135`); healthy on Python 3.14.7.
- Used only by flet's `TemplateRoute` (`flet\controls\template_route.py:3, 44`) and `Router`
  (`flet\components\router.py:16, 191, 228, 265, 287, 302`) — **the app uses neither** (0 hits for
  `repath`, `TemplateRoute`, `Router`, `page.go`, `page.route`, `on_route_change` in `src/`+`tests/`).
- The app's navigation is a local-state screen switch (`src\app_shell.py:707-708, 725-728, 909-932`;
  `src\main.py:588`) with a single view (`src\main.py:587, 606-614`) — no URL, no route table, no
  hand-rolled parser. `repath` becomes a genuine opportunity **only** if the app later adopts deep
  linking, and then the vehicle is flet's `ft.Router`/`ft.TemplateRoute` (still zero new deps), not a
  direct `import repath`.
- Watch item only: `repath` drags in `six` 1.17.0 (unmaintained). That is flet's transitive
  problem; it surfaces here only if someone bypasses flet's public API.
