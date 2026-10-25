# colorama 0.4.6 — dependency audit (Sherlock V3)

Source of truth: the installed `.venv` only. No app file was modified.

## 1) Installed verification

| Item | Evidence |
|---|---|
| Version | `colorama/__init__.py:6` → `__version__ = '0.4.6'`; `colorama-0.4.6.dist-info/METADATA` → `Version: 0.4.6` |
| Installed files | `colorama/{__init__,ansi,ansitowin32,initialise,win32,winterm}.py` |
| Declared by | `user_scanner-1.5.2.3.dist-info/METADATA` → `Requires-Dist: colorama>=0.4,<1`; `phonsint-0.1.0.dist-info/METADATA` → `colorama>=0.4.0,<1.0.0`; `pytest-9.1.1.dist-info/METADATA` → `colorama>=0.4; sys_platform == "win32"` |
| Not a real edge | `pygments-2.21.0.dist-info/METADATA` → `colorama>=0.4.6; extra == 'windows-terminal'` (extra only; pygments never imports it) |
| Key mechanic | `colorama/ansi.py:7` → `CSI = '\033['`. `Fore`/`Style` are **raw ANSI escape strings**; importing colorama hands out escape codes whether or not `init()` ever ran. `init()` only affects *stdout write* behaviour. |
| `init()` impl | `colorama/initialise.py:37-62`. `initialise.py:48-50`: `if sys.stdout is None: wrapped_stdout = None` (no wrap). `initialise.py:53-57`: stderr still wrapped. `initialise.py:60-62`: `atexit.register(reset_all)`. |

## 2) In-venv importers (file:line)

**Import only (no `init()`)** — these are the ones the app actually reaches:
- `user_scanner/core/result.py:5` — `from colorama import Fore, Style`
- `user_scanner/core/hudson.py:3` — `from colorama import Fore, Style`
- `user_scanner/core/cross_scan.py:16`, `user_scanner/core/orchestrator.py:10`, `user_scanner/core/loud_prompt.py:3`, `user_scanner/core/email_orchestrator.py:7`, `user_scanner/utils/update.py:3`, `user_scanner/utils/updater_logic.py:1`, `user_scanner/cli/tips.py:5`, `user_scanner/__main__.py:8`
- `phonsint/core/result.py:6`, `phonsint/core/orchestrator.py:5`
- `_pytest/capture.py:78` — `import colorama  # noqa: F401` (win32 import-order workaround, `_pytest/capture.py:68-81`, called at `_pytest/capture.py:160`)
- `_pytest/_io/terminalwriter.py:80,84` — `import colorama` → `colorama.AnsiToWin32(file).stream`

**Module-level `init()` (only reached via CLI entry points, never by the app):**
- `phonsint/__main__.py:6` (import) + **`phonsint/__main__.py:15` → `init(autoreset=True)`**
- `user_scanner/cli/banner.py:1` (import) + **`user_scanner/cli/banner.py:6` → `init(autoreset=True)`**

**App never imports colorama directly:** `grep -rn "colorama" src/ tests/` → **0 hits**. The app reaches upstream modules only via `src/services/user_scanner_compat.py` (the declared glue layer, `user_scanner_compat.py:1-13`), incl. `user_scanner.core.result` (`user_scanner_compat.py:185`, `email_service.py:113`) and `phonsint.core.result` (`user_scanner_compat.py:350`, `phone_service.py:51`).

## 3) App-process reality (real command outputs)

```
$ .venv/Scripts/python.exe -c "import user_scanner.core.result, sys; print('colorama' in sys.modules)"
True
$ .venv/Scripts/python.exe -c "import phonsint.core.result, sys; print('colorama' in sys.modules)"
True
```

After importing the app's own service layer (`PYTHONPATH=src`):
```
after services.user_scanner_compat: colorama in sys.modules= True  wrapped_stdout= None  wrapped_stderr= None
after services.phone_service:        colorama= True  wrapped_stdout= None
after services.email_service:        colorama= True  wrapped_stdout= None
stdout type= TextIOWrapper   (sys.stdout is NOT wrapped)
phonsint.__main__ imported= False
user_scanner.cli.banner imported= False
colorama.initialise.atexit_done (init() ran?) = False
colorama.initialise.wrapped_stdout = None
```

**Conclusion: `colorama.init()` NEVER executes in the app process.** Both `init()` call sites live in `__main__`/CLI modules that the app never imports. `colorama` is imported (constants only), stdout is never wrapped, and `sys.stdout` stays a plain `TextIOWrapper`.

## 4) ANSI leak risk + concrete fix location

**The obvious leak is closed.** `grep -rn "get_console_output\|console_output" src/ tests/` → **0 hits**: the app never calls `Result.get_console_output()` (`phonsint/core/result.py:231`, `user_scanner/core/result.py:254`), the only producer of ANSI-decorated result strings. The app renders structured fields only — `Status.to_label()` (`phonsint/core/result.py:68-73`) and `Result.get_reason()`/`__str__` (`phonsint/core/result.py:151-162,203-204`) — both plain text with no `Fore`/`Style`.

**But one real leak path remains — upstream stdout capture (Hudson Rock check).**
- `src/services/sherlock_service.py:276-291` and `src/services/email_service.py:414-428` run `hudson.run_hudson_scan(...)` under `contextlib.redirect_stdout(io.StringIO())` and return `buf.getvalue().strip()`.
- Upstream prints raw ANSI into that buffer: `user_scanner/core/hudson.py:8-13` (colour constants) used at `hudson.py:30-33,40-47`; `user_scanner/cli/tips.py:53-60` (`print_hudson_remediation_tip`).
- The captured string is returned to the GUI and shown verbatim in a SnackBar: `src/screens/home_screen.py:587` → `home_screen.py:591`; `src/main.py:1120-1123`; `src/main.py:1576-1579`.
- Verified capture (real upstream function):
  `'\x1b[33m\x1b[1m[!] Security Notice:\x1b[0m All credentials saved on infected computers are at risk.\n    \x1b[36m\x1b[1mRemediation tools:\x1b[0m Visit \x1b[36mhttps://www.hudsonrock.com/free-tools\x1b[0m for identity monitoring.'`
- There is **no ANSI stripper anywhere in `src/`** (`grep -rniE "ansi|\\x1b|\\033"` → no strip helper), so any upstream coloured text is a latent leak.
- **Fix location:** strip ANSI at the two capture boundaries — `src/services/sherlock_service.py:290` and `src/services/email_service.py:427` (both `return buf.getvalue().strip()`) — e.g. `re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", buf.getvalue()).strip()`, ideally via one shared helper (e.g. `src/core/format.py`).

**Packaged / windowless-build risk (the Flet `sys.stdout=None` scenario):**
- `python -c "import sys; sys.stdout=None; import colorama; colorama.init()"` → **no exception**. `init_ok=True`, `wrapped_stdout=None`, `wrapped_stderr=<StreamWrapper>`, `sys.stdout` stays `None`. Guarded by `initialise.py:48-50` / `53-57`.
- `print()` with `sys.stdout is None` is a **silent no-op** in CPython (no exception).
- So even in a windowless build colorama is None-safe, and in this app `init()` never runs at all → **no wrapped-stdout hazard**.
- Adjacent (not colorama) windowless risk on the same code path: `user_scanner/core/hudson.py:36` calls `input()` inside `check_hudson_permission()`, and `helpers.py:749` defaults `auto_hudson_prompt: True` → the GUI worker can block on stdin. The app catches it (`sherlock_service.py:287`) and shows "Hudson check failed: …".

## 5) Verdict

**LOW RISK / ship as-is, with one caveat.**

- colorama is a **transitive, import-only** dependency for the running app (user-scanner + phonsint; pytest is a dev/win32-only edge). The app never imports it directly.
- `colorama.init()` **never executes** in the app process → stdout is never wrapped, `sys.stdout=None` (windowless build) is handled safely by `initialise.py:48-50` with no crash.
- `get_console_output()` ANSI strings **never reach `ft.Text`** — the app never calls them and only uses plain-text status/reason fields.
- **One real (cosmetic) ANSI leak**: the Hudson Rock stdout capture returns upstream ANSI into a SnackBar (`sherlock_service.py:290`, `email_service.py:427` → `home_screen.py:591`, `main.py:1123`, `main.py:1579`). Fix = strip escapes at those two `return` sites. No other leak path exists today; consider a shared strip helper in `src/core/format.py` as cheap insurance for future upstream text.
