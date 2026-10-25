# rich 15.0.0 Dependency Reference & Architectural Study

**Target Package:** `rich` v15.0.0  
**Environment Path:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/rich`  
**Distribution Metadata:** `rich-15.0.0.dist-info`  
**Target Document:** `/home/maikel/.zcode/workspace/default/Sherlock-V2/docs/reference/dep-rich.md`  

---

## 1. Executive Summary

`rich` (version 15.0.0) is a Python library for rich text and terminal formatting in command-line interfaces. In the Sherlock-V2 ecosystem, `rich` is installed as a direct/transitive dependency alongside `colorama`, `user-scanner`, `phonsint`, and `flet`.

Within the CLI versions of `user-scanner` (v1.5.2.3) and `phonsint` (v0.1.0), `rich` is used primarily for:
1. **Dynamic Progress Bars:** Multi-column progress rendering (`Progress`, `SpinnerColumn`, `BarColumn`, `MofNCompleteColumn`, `TextColumn`) during concurrent asynchronous scanning.
2. **Tabular & Panel Displays:** Formatted module catalogs and category listings (`Console`, `Table`, `Panel`, `box`).
3. **Console Markup:** In-line BBCode-style color and style annotations (`[bold cyan]`, `[white]`, `[dim]`).

**Critical Architectural Consideration for Sherlock-V2 (Flet GUI):**  
In a Flet GUI desktop application, **code must NOT call Rich's `Progress` or `print()` directly**. Flet communicates with a client-side Flutter engine that renders native UI controls (widgets on a canvas) rather than an ANSI character-cell terminal. Calling `rich.print()` or `Progress` directly bypasses the GUI, spews unrendered ANSI control codes (`\x1b[...]`) and carriage returns (`\r`), blocks the asyncio event loop, and causes graphical freezing or data loss. This document details the exact mechanics of Rich 15.0.0, audits its current usage across Sherlock-V2's underlying scan engines, and prescribes adaptation patterns for Flet.

---

## 2. Package Identity & Environment Context

- **Installed Version:** `15.0.0` (Verified via `importlib.metadata.version("rich")` and `rich-15.0.0.dist-info/METADATA`).
- **Python Environment:** Python 3.14.7 (`/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Scripts/python.exe`).
- **Core Dependencies:**
  - `markdown-it-py >= 4.0.0` (Markdown parsing)
  - `pygments >= 2.13.0` (Code syntax highlighting)
  - `typing-extensions >= 4.0.0` (Typing support)
- **Top-Level Package Exports (`rich/__init__.py:1-40`):**
  - High-level print: `from rich import print, inspect, get_console, reconfigure`
  - Re-exported classes: `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel`, `rich.progress.Progress`, `rich.text.Text`, `rich.style.Style`, `rich.theme.Theme`, `rich.box`.

---

## 3. Core Rich Components in Rich 15.0.0

### 3.1 Console (`rich/console.py`)

The `Console` class is the central coordinator for rendering renderables, managing terminal dimensions, styles, output streams, and legacy Windows translation.

- **Class Definition & Constructor (`rich/console.py:581-652`):**
  ```python
  class Console:
      def __init__(
          self,
          *,
          color_system: Optional[Literal["auto", "standard", "256", "truecolor", "windows"]] = "auto",
          force_terminal: Optional[bool] = None,
          force_jupyter: Optional[bool] = None,
          force_interactive: Optional[bool] = None,
          soft_wrap: bool = False,
          theme: Optional[Theme] = None,
          stderr: bool = False,
          file: Optional[IO[str]] = None,
          quiet: bool = False,
          width: Optional[int] = None,
          height: Optional[int] = None,
          style: Optional[StyleType] = None,
          no_color: Optional[bool] = None,
          tab_size: int = 8,
          record: bool = False,
          markup: bool = True,
          emoji: bool = True,
          emoji_variant: Optional[EmojiVariant] = None,
          highlight: bool = True,
          log_time: bool = True,
          log_path: bool = True,
          log_time_format: Union[str, FormatTimeCallable] = "[%X]",
          highlighter: Optional["HighlighterType"] = ReprHighlighter(),
          legacy_windows: Optional[bool] = None,
          safe_box: bool = True,
          get_datetime: Optional[Callable[[], datetime]] = None,
          get_time: Optional[Callable[[], float]] = None,
          _environ: Optional[Mapping[str, str]] = None,
      ):
  ```
- **Key Methods & Attributes:**
  - `console.print(*objects, ...)` (`rich/console.py:1675`): Formats renderables and writes formatted segments to `self.file` (defaults to `sys.stdout`).
  - `console.log(*objects, ...)` (`rich/console.py:1738`): Outputs structured logs with timestamps and caller file/line metadata.
  - `console.capture()` (`rich/console.py:2296`): Context manager returning a `Capture` object that stores output segments without writing to stdout.
  - `console.export_text(clear=True, styles=False)` (`rich/console.py:2320`): Exports recorded output as plain text.
  - `console.export_html(clear=True, ...)` (`rich/console.py:2339`): Exports recorded output as styled HTML.
  - `console.export_svg(...)` (`rich/console.py:2378`): Exports recorded terminal output as vector SVG.
  - `self.width` / `self.height` (`rich/console.py:1008-1044`): Terminal size detection via `shutil.get_terminal_size()`. When running in headless GUI environments without a tty, defaults to 80x25 or environmental overrides.
  - `self._lock` (`rich/console.py:714`): Internal re-entrant lock (`threading.RLock`) providing thread safety across concurrent prints.

---

### 3.2 Progress System (`rich/progress.py`)

The `Progress` system displays animated, self-updating progress bars. It operates via an active background render loop powered by `rich.live.Live`.

- **Class Definition (`rich/progress.py:1061-1112`):**
  ```python
  class Progress(JupyterMixin):
      def __init__(
          self,
          *columns: Union[str, ProgressColumn],
          console: Optional[Console] = None,
          auto_refresh: bool = True,
          refresh_per_second: float = 10,
          speed_estimate_period: float = 30.0,
          transient: bool = False,
          redirect_stdout: bool = True,
          redirect_stderr: bool = True,
          get_time: Optional[GetTimeCallable] = None,
          disable: bool = False,
          expand: bool = False,
      ) -> None:
  ```
- **Internal Mechanics & Terminal Control:**
  - **Live Loop (`rich/progress.py:1100-1108`):** Instantiates `Live(auto_refresh=auto_refresh, refresh_per_second=10, transient=transient, redirect_stdout=True)`.
  - **Terminal Redraws:** The `Live` display continually calculates rendered lines, repositions the terminal cursor to the top of the progress area using ANSI cursor codes (`\x1b[F` / `\x1b[A`) and carriage returns (`\r`), and overwrites previous frames.
  - **Transient Mode (`transient=True`):** Erases the progress display from the terminal upon exiting the context manager (`progress.stop()`).
  - **Stdout Redirection (`redirect_stdout=True`):** Proxies standard `print()` calls so output appears cleanly above the progress bar in supported terminals.

#### Progress Columns Used in Sherlock-V2

Sherlock-V2's underlying engines consistently configure a 5-column layout:
```python
Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    transient=True,
)
```

1. **`SpinnerColumn` (`rich/progress.py:566-613`):**
   - Renders an animated Unicode spinner.
   - Defaults: `spinner_name="dots"`, `style="progress.spinner"`, `speed=1.0`, `finished_text=" "`.
   - The animation frame changes dynamically on each refresh cycle based on elapsed monotonic time.
2. **`TextColumn` (`rich/progress.py:616-644`):**
   - Renders arbitrary formatted text strings containing `{task}` field substitutions (e.g. `{task.description}`, `{task.percentage:>3.0f}%`).
   - Supports rich markup (`markup=True`) and optional regex/syntax highlighters (`highlighter`).
3. **`BarColumn` (`rich/progress.py:646-675`):**
   - Renders the graphical progress bar itself.
   - Parameters: `bar_width=40` (or `None` for full-width responsive expansion), `style="bar.back"`, `complete_style="bar.complete"`, `finished_style="bar.finished"`, `pulse_style="bar.pulse"`.
   - When `task.total is None`, renders an indeterminate pulsing bar.
4. **`MofNCompleteColumn` (`rich/progress.py:838-863`):**
   - Displays numeric progress in completed/total format (e.g., ` 12/100`).
   - Right-pads the completed count based on the number of digits in `total`, preventing horizontal jitter as powers of 10 are crossed.

#### Task Management API (`rich/progress.py:1417-1639`)

- `progress.add_task(description, total=100.0, completed=0, visible=True, **fields) -> TaskID` (`rich/progress.py:1600`): Registers a new task and returns an integer ID.
- `progress.update(task_id, *, total=None, completed=None, advance=None, description=None, visible=None, refresh=False, **fields)` (`rich/progress.py:1417`): Modifies task state, updates description text, or sets completion count.
- `progress.advance(task_id, advance=1)` (`rich/progress.py:1517`): Increments `task.completed` by `advance` and records sample timestamps for speed/ETA calculation.

---

### 3.3 Table & Table.grid (`rich/table.py`)

`Table` organizes content into rows and columns with configurable borders, padding, headers, and alignments.

- **Class Definition (`rich/table.py:153-222`):**
  - Parameters: `title`, `caption`, `box` (default `box.HEAVY_HEAD`), `padding=(0, 1)`, `expand=False`, `show_header=True`, `border_style=None`.
  - Column addition: `table.add_column(header="", style=None, justify="left", width=None, ratio=None, no_wrap=False)` (`rich/table.py:364-420`).
  - Row addition: `table.add_row(*renderables, style=None, end_section=False)` (`rich/table.py:422-438`).
- **`Table.grid()` Classmethod (`rich/table.py:253-284`):**
  - Factory method producing a borderless, headerless table structure:
    ```python
    @classmethod
    def grid(cls, *headers, padding=0, collapse_padding=True, pad_edge=False, expand=False) -> "Table":
        return cls(*headers, box=None, padding=padding, collapse_padding=collapse_padding,
                   show_header=False, show_footer=False, show_edge=False, pad_edge=pad_edge, expand=expand)
    ```
  - Used in `user_scanner/__main__.py:312, 343` to create multi-column layouts and responsive card grids.

---

### 3.4 Panel (`rich/panel.py`)

`Panel` draws decorative border boxes around any renderable.

- **Class Definition (`rich/panel.py:17-72`):**
  - Parameters: `renderable`, `box=box.ROUNDED`, `title=None`, `title_align="center"`, `subtitle=None`, `border_style="none"`, `padding=(0, 1)`, `expand=True`.
  - Alternative constructor `Panel.fit(renderable, ...)` (`rich/panel.py:74-91`): Shrinks the panel width to fit the contents rather than stretching across the entire terminal width (`expand=False`).
  - Used in `user_scanner/__main__.py:330-338` to frame category module listings.

---

### 3.5 Console Markup (`rich/markup.py`)

Rich provides a tags-based markup syntax reminiscent of BBCode.

- **Tag Syntax (`rich/markup.py:12-41`):**
  - Format: `[style]text[/style]` or `[tag=parameter]text[/tag]`. Short closing tags `[/]` close the most recently opened tag.
  - Examples: `[bold cyan]Text[/bold cyan]`, `[white]• Module[/white]`, `[dim]info[/dim]`.
- **Escaping Text (`rich/markup.py:48-71`):**
  - `rich.markup.escape(markup: str) -> str`: Escapes unescaped brackets (`\[`) to prevent dynamic content (e.g. user input, URLs, scan reasons) from corrupting the markup parser.
- **Rendering (`rich/markup.py:106-160`):**
  - `rich.markup.render(markup: str) -> Text`: Parses markup tags into a `rich.text.Text` object containing styled character `Span` objects.

---

### 3.6 Colorama Integration & Windows Console Handling

A frequent point of confusion in terminal toolchains is the interaction between `rich` and `colorama`.

1. **Rich's Native Windows Implementation:**
   - **No Dependency on Colorama:** `rich` does **not** depend on or call `colorama`.
   - **Virtual Terminal Detection (`rich/_windows.py:25-62`):** Rich queries the console handle with `GetConsoleMode(GetStdHandle())` via CTypes. If `ENABLE_VIRTUAL_TERMINAL_PROCESSING` (0x0004) is enabled, Windows natively handles ANSI sequences.
   - **Legacy Windows Translation (`rich/_windows_renderer.py:7-57` & `rich/_win32_console.py`):** On older Windows consoles (e.g., Windows 7/8 or Windows 10 without VT enabled), `detect_legacy_windows()` evaluates to `True` (`rich/console.py:576`). Rich intercepts ANSI styled segments and converts them directly into Win32 Console API calls (`SetConsoleTextAttribute`, `SetConsoleCursorPosition`) using `LegacyWindowsTerm`.
2. **Coexistence with Colorama in Sherlock-V2 Engines:**
   - `phonsint/__main__.py:6, 15` explicitly imports `colorama` and calls `init(autoreset=True)`.
   - `user_scanner/core/result.py:5` and `phonsint/core/result.py:6` format console strings using `colorama.Fore` (`Fore.GREEN`, `Fore.RED`, `Fore.YELLOW`, `Fore.CYAN`) and `colorama.Style` (`Style.RESET_ALL`).
   - **The Conflict:** When `colorama.init()` is executed, it wraps `sys.stdout` in an `AnsiToWin32` proxy stream.
     - If code prints raw `colorama` ANSI strings directly via standard `print()` while Rich `Progress` is concurrently redrawing the terminal, the ANSI codes bypass Rich's segment buffer.
     - In modern terminals this can lead to line corruption; in non-terminal environments (such as GUI apps), the raw escape sequences (`\x1b[32m`, `\x1b[0m`) remain unparsed.

---

## 4. Usage Audit: `user-scanner` and `phonsint`

Both `user-scanner` and `phonsint` are integrated into Sherlock-V2. Below is the file-by-file audit of how each library employs `rich` and standard printing.

### 4.1 `user-scanner` (v1.5.2.3)

| File | Lines | Component / Usage | Description |
| :--- | :--- | :--- | :--- |
| `user_scanner/__main__.py` | `293-296` | Dynamic Imports | Imports `Console`, `Panel`, `Table`, `box` inside `--list-user` / `--list-email`. |
| `user_scanner/__main__.py` | `298-299` | `Console()` & Width | Creates `console = Console()` and dynamically sets grid columns based on `console.width`. |
| `user_scanner/__main__.py` | `312-329` | `Table.grid()` | Builds inner 1- or 2-column grid for module lists with markup `[white]• {name}[/white]`. |
| `user_scanner/__main__.py` | `330-338` | `Panel()` | Wraps inner table in `box.ROUNDED` cyan panel with bold magenta category title. |
| `user_scanner/__main__.py` | `341-352` | `console.print()` | Prints header and outer responsive `Table.grid()` containing all category panels. |
| `user_scanner/__main__.py` | `353-364` | `except ImportError` | Graceful fallback to raw Colorama/print if Rich is missing. |
| `user_scanner/core/orchestrator.py` | `24` | Import | `from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn` |
| `user_scanner/core/orchestrator.py` | `108-115` | `Progress(...)` | Context manager configured with 5 columns and `transient=True` in `_run_batch()`. |
| `user_scanner/core/orchestrator.py` | `116-120` | Task Management | `progress.add_task(...)` and `on_start_cb` updating task description with current site name. |
| `user_scanner/core/orchestrator.py` | `136` | `progress.advance()` | Attached via `t.add_done_callback(lambda t: progress.advance(task_id))`. |
| `user_scanner/core/orchestrator.py` | `147, 156` | Direct `print()` | Prints category banner (`== CATEGORY SITES ==`) directly to stdout while Progress is live. |
| `user_scanner/core/orchestrator.py` | `159` | Direct `print()` | Calls `result.show(configs)`, which executes `print(self.get_console_output())`. |
| `user_scanner/core/orchestrator.py` | `211-256` | `Progress(...)` | Identical Progress setup inside `_run_user_full_async()`. |
| `user_scanner/core/email_orchestrator.py`| `21` | Import | Same 5 Progress columns imported for email reconnaissance. |
| `user_scanner/core/email_orchestrator.py`| `135-165` | `Progress(...)` | Same Progress setup, task advance callback, and interleaved stdout prints. |
| `user_scanner/core/email_orchestrator.py`| `259-285` | `Progress(...)` | Same Progress setup inside `_run_email_full_batch_async()`. |
| `user_scanner/core/pdf_generator.py` | `15-18` | Guarded Import | `try: from rich.progress import ...; RICH_AVAILABLE = True except ImportError: ...` |
| `user_scanner/core/pdf_generator.py` | `229-242` | `Progress(...)` | Used in `download_images_parallel()` to display image download progress. |
| `user_scanner/core/result.py` | `5` | `colorama` Import | Imports `Fore, Style` for result string colorization. |
| `user_scanner/core/result.py` | `238-286` | Output Formatting | `get_console_output()` constructs ANSI strings using `Fore.GREEN`, `Fore.RED`, `Fore.CYAN`, tree connectors (`├──`, `└──`), and icons (`[✔]`, `[✘]`). |
| `user_scanner/core/result.py` | `303` | `print()` | `show()` executes `print(self.get_console_output(configs))`. |

---

### 4.2 `phonsint` (v0.1.0)

| File | Lines | Component / Usage | Description |
| :--- | :--- | :--- | :--- |
| `phonsint/__main__.py` | `6` | `colorama` Import | `from colorama import Fore, Style, init` |
| `phonsint/__main__.py` | `12-13` | Rich Import | `from rich.console import Console; from rich.table import Table` |
| `phonsint/__main__.py` | `15` | `init()` | `init(autoreset=True)` called at module level. |
| `phonsint/__main__.py` | `16` | `Console()` | Instantiates global `console = Console()`. |
| `phonsint/__main__.py` | `41-52` | `Table()` | Creates cyan table with Category (magenta), Module (green), Path (dim white) columns and calls `console.print(table)`. |
| `phonsint/__main__.py` | `29, 115, 140`| Direct `print()` | Prints ASCII banner, phone verification notice, and scan summary with Colorama. |
| `phonsint/core/orchestrator.py` | `6` | Import | `from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn` |
| `phonsint/core/orchestrator.py` | `116-123` | `Progress(...)` | Configures 5-column Progress with `transient=True`. |
| `phonsint/core/orchestrator.py` | `124-128` | Task Management | `progress.add_task(f"[cyan]Scanning {phone_info.e164}...", total=total_modules)` and description updater. |
| `phonsint/core/orchestrator.py` | `143` | `progress.advance()` | `t.add_done_callback(lambda _: progress.advance(task_id))` increments progress upon worker completion. |
| `phonsint/core/orchestrator.py` | `153, 161, 164`| Direct `print()` | Prints category headings and calls `result.show(configs)` while Progress is active. |
| `phonsint/core/result.py` | `6` | `colorama` Import | Imports `Fore, Style` for terminal ANSI coloring. |
| `phonsint/core/result.py` | `215-260` | Output Formatting | Formats result line with Colorama colors, status icons (`[✔]`, `[✘]`, `[!]`, `[~]`), and extra tree branches. |
| `phonsint/core/result.py` | `275` | `print()` | `show()` executes `print(self.get_console_output(configs))`. |

---

## 5. Why Direct Rich Calls Are Prohibited in a Flet GUI

Sherlock-V2 provides a modern desktop GUI interface built on **Flet** (`flet >= 1.0.4`). Under no circumstances should backend scan routines or GUI event handlers invoke Rich's `Progress`, `console.print()`, or Python's `print()` directly.

```
       CLI Execution Path                         Flet GUI Execution Path
┌─────────────────────────────────┐         ┌─────────────────────────────────┐
│     Orchestrator / Engine       │         │     Orchestrator / Engine       │
└──────────────┬──────────────────┘         └──────────────┬──────────────────┘
               │                                           │ (Event / Callback)
     Direct rich.print() /                                 ▼
       Progress() Calls                     ┌─────────────────────────────────┐
               │                            │      Sherlock-V2 Adapter        │
               ▼                            └──────────────┬──────────────────┘
┌─────────────────────────────────┐                        │ (State Mutation)
│   Standard Output (stdout)      │                        ▼
│  • ANSI Escape Codes (\x1b)     │         ┌─────────────────────────────────┐
│  • Carriage Returns (\r)        │         │      Flet Python Runtime        │
│  • Terminal Cursor Moves        │         └──────────────┬──────────────────┘
└──────────────┬──────────────────┘                        │ (JSON RPC / WebSocket)
               │                                           ▼
               ▼                            ┌─────────────────────────────────┐
┌─────────────────────────────────┐         │      Flutter Engine (GUI)       │
│ Terminal / Character-Cell VT    │         │  • Canvas / Vector Rendering    │
│ (Renders in-place terminal UI)  │         │  • ft.ProgressBar, ft.ListView  │
└─────────────────────────────────┘         └─────────────────────────────────┘
```

The fundamental technical reasons prohibiting direct Rich/print calls in Flet include:

### 5.1 Architecture Disconnect: Terminal Streams vs. Reactive Widget Tree
- **Rich's Model:** Rich assumes standard POSIX/Win32 standard streams (`sys.stdout`, `sys.stderr`) backed by an ANSI-compatible character grid of known width and height.
- **Flet's Model:** Flet runs an async Python service that connects over WebSockets/IPC to a Flutter frontend. The Flutter client renders vector graphics and UI widgets on a canvas. Standard output is completely uncoupled from the GUI visual hierarchy.

### 5.2 Stdout Discarded or Missing in Packaged Desktop Apps
- When a Flet app is distributed or packaged (e.g. `flet pack`, `pyinstaller -w`, or launched via `pythonw.exe`), the OS creates no console window.
- In these environments, `sys.stdout` and `sys.stderr` are set to `None` or piped to `/dev/null`.
- Any code attempting `print()` or `console.print()` will either silently fail or raise `AttributeError: 'NoneType' object has no attribute 'write'`.

### 5.3 ANSI Escape Code Corruption
- If standard output is naively intercepted and injected into a Flet widget (e.g., `ft.Text(value=captured_stdout)`):
  - Flet does **not** interpret raw terminal ANSI escape sequences.
  - The UI displays garbled ASCII strings:
    ```
    \x1b[32m[✔]\x1b[0m GitHub: \x1b[32mFound\x1b[0m
    \x1b[36m      └── followers: 42\x1b[0m
    ```
  - This severely impairs the user experience.

### 5.4 Cursor Control & Carriage Returns Cause Buffer Explosions
- Rich's `Progress` updates at 10 Hz (`refresh_per_second=10`). In a terminal, it repeatedly overwrites the current line using carriage returns (`\r`), cursor-up (`\x1b[1A`), and erase-line (`\x1b[2K`) commands.
- GUI text widgets (`ft.Text`, `ft.ListView`) do **not** support terminal cursor positioning:
  - Every carriage return is either treated as a newline or concatenated.
  - Over a 30-second scan across 300 sites, Rich emits **over 300 progress frames**, flooding the GUI buffer with thousands of redundant lines, causing severe UI lag, memory spikes, and screen flickering.

### 5.5 Asyncio Event Loop Clashes & Thread Deadlocks
- Flet operates on an asynchronous event loop (`asyncio`).
- Both `user-scanner` (`run_user_full()` at `user_scanner/core/orchestrator.py:259`) and `phonsint` (`run_scan()` at `phonsint/core/orchestrator.py:170`) wrap their scans with `asyncio.run()`.
- Calling `asyncio.run()` from inside an active Flet event handler triggers:
  ```
  RuntimeError: asyncio.run() cannot be called from a running event loop
  ```
- If a blocking synchronous scan is called on the main thread, Flet's UI loop freezes, the Flutter window stops rendering, and the operating system marks the application as "Not Responding".

---

## 6. Adaptation Strategy & Integration Patterns for Flet

To integrate `user-scanner` and `phonsint` cleanly into Sherlock-V2 without touching terminal streams, follow these architectural patterns.

### 6.1 Pattern 1: Event-Driven Observer Protocol (Recommended)

Decouple scan execution from presentation by replacing stdout printing with an observer/listener protocol.

```python
from typing import Protocol, Any, Optional
from user_scanner.core.result import Result

class ScanProgressObserver(Protocol):
    """Observer interface decoupling scan execution from UI rendering."""
    
    def on_scan_start(self, target: str, total_modules: int) -> None:
        """Called when a scan starts."""
        ...
        
    def on_module_start(self, site_name: str) -> None:
        """Called when a module starts executing."""
        ...
        
    def on_module_complete(self, completed: int, total: int) -> None:
        """Called when a module finishes executing."""
        ...
        
    def on_result(self, result: Result) -> None:
        """Called as soon as a single result is resolved."""
        ...
        
    def on_scan_complete(self, results: list[Result]) -> None:
        """Called when the entire scan finishes."""
        ...
```

### 6.2 Pattern 2: Mapping Rich CLI Constructs to Flet Widgets

| Rich CLI Construct | Rich Code Location | Flet GUI Replacement | Flet Implementation Detail |
| :--- | :--- | :--- | :--- |
| `Progress()` | `rich/progress.py:1061` | `ft.ProgressBar` | Set `progress_bar.value = completed / total`. Set `value = None` for indeterminate/pulsing state. |
| `SpinnerColumn()` | `rich/progress.py:566` | `ft.ProgressRing` | Use a small `ft.ProgressRing(width=16, height=16, stroke_width=2)` beside active task indicators. |
| `TextColumn("{task.description}")` | `rich/progress.py:616` | `ft.Text()` | Dynamic label: `ft.Text(f"Scanning {target}... ({current_site})")`. |
| `MofNCompleteColumn()` | `rich/progress.py:838` | `ft.Text()` | Counter badge: `ft.Text(f"{completed} / {total}", weight=ft.FontWeight.BOLD)`. |
| `Table()` (Result Display) | `rich/table.py:153` | `ft.DataTable` or `ft.ListView` | Render results as interactive rows with clickable links, status badges, and action buttons. |
| `Panel()` (Category Framing) | `rich/panel.py:17` | `ft.Card` / `ft.Container` | Container with border, border radius, background color, and title header. |
| `result.show()` (Console ANSI) | `user_scanner/core/result.py:298` | `ft.ListTile` / `ft.ExpansionTile` | Show site name, status icon (`ft.Icons.CHECK_CIRCLE` in green), URL button, and metadata tree. |

---

### 6.3 Pattern 3: Concrete Flet Adapter Implementation

The following complete adapter pattern demonstrates how Sherlock-V2 connects asynchronous scan routines directly to Flet reactive state without calling Rich:

```python
import asyncio
import flet as ft
from user_scanner.core.helpers import ScanConfig, load_categories, load_modules
from user_scanner.core.orchestrator import _async_worker
from user_scanner.core.result import Result, Status

class FletScanView(ft.Column):
    """Self-contained Flet component for running scans with live reactive UI."""

    def __init__(self, page: ft.Page):
        super().__init__(expand=True)
        self.page = page

        # 1. Native Flet Progress Controls
        self.status_text = ft.Text("Ready", size=14, weight=ft.FontWeight.W_500)
        self.progress_bar = ft.ProgressBar(value=0.0, width=500, visible=False)
        self.counter_text = ft.Text("", size=12, color=ft.Colors.GREY_400)
        self.spinner = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)

        # 2. Results List View
        self.results_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)

        self.controls = [
            ft.Row([self.spinner, self.status_text, self.counter_text], alignment=ft.MainAxisAlignment.START),
            self.progress_bar,
            ft.Divider(),
            self.results_list,
        ]

    async def start_user_scan(self, username: str, configs: ScanConfig):
        """Runs the username scan asynchronously without Rich Progress or stdout pollution."""
        self.results_list.controls.clear()
        self.progress_bar.value = 0.0
        self.progress_bar.visible = True
        self.spinner.visible = True
        self.status_text.value = f"Preparing scan for '{username}'..."
        self.page.update()

        # Load modules
        categories = list(load_categories(no_nsfw=configs.no_nsfw).items())
        modules = []
        for cat_name, cat_path in categories:
            modules.extend(load_modules(cat_path))

        total_modules = len(modules)
        completed_count = 0
        sem = asyncio.Semaphore(configs.concurrency if hasattr(configs, "concurrency") else 40)

        # Update progress callback
        def on_module_start(site_name: str):
            self.status_text.value = f"Scanning {username}... ({site_name})"
            self.page.update()

        # Spawn tasks directly on Flet's asyncio loop
        tasks = [
            asyncio.create_task(
                _async_worker(
                    module=mod,
                    username=username,
                    sem=sem,
                    configs=configs,
                    on_start=on_module_start
                )
            )
            for mod in modules
        ]

        # Stream results as they complete
        for coro in asyncio.as_completed(tasks):
            result: Result = await coro
            completed_count += 1
            
            # Update native progress
            self.progress_bar.value = completed_count / total_modules
            self.counter_text.value = f"{completed_count}/{total_modules}"

            # Only add visible results to GUI
            if configs.show_all or result.is_visible(configs):
                self._add_result_tile(result)

            self.page.update()

        self.spinner.visible = False
        self.status_text.value = f"Scan complete for '{username}'."
        self.page.update()

    def _add_result_tile(self, result: Result):
        """Converts a Result model into a styled native Flet component."""
        is_taken = result.status == Status.TAKEN
        icon_color = ft.Colors.GREEN if is_taken else (ft.Colors.AMBER if result.status == Status.ERROR else ft.Colors.RED)
        icon_name = ft.Icons.CHECK_CIRCLE if is_taken else (ft.Icons.WARNING if result.status == Status.ERROR else ft.Icons.CANCEL)

        # Build extra metadata tags
        extra_controls = []
        if result.extra:
            for k, v in result.extra.items():
                extra_controls.append(ft.Text(f"• {k}: {v}", size=12, color=ft.Colors.GREY_300))

        tile = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon_name, color=icon_color, size=20),
                        ft.Text(result.site_name, weight=ft.FontWeight.BOLD, size=14),
                        ft.Container(expand=True),
                        ft.Text(result.status.to_label(), color=icon_color, size=12, weight=ft.FontWeight.BOLD),
                    ]),
                    ft.Text(result.url, size=12, color=ft.Colors.BLUE_400) if result.url else ft.Container(),
                    *extra_controls,
                ], spacing=4),
                padding=10,
            ),
            elevation=1,
        )
        self.results_list.controls.append(tile)
```

---

### 6.4 Pattern 4: Capturing Rich Output When Text/Log Emulation is Required

If Sherlock-V2 includes a "Raw Output" or "Terminal Log" tab where formatted Rich text is explicitly desired, use `Console(record=True)` or `console.capture()` to extract clean text or HTML without writing to standard streams:

```python
from rich.console import Console

# Create an isolated memory console
mem_console = Console(record=True, width=80, color_system="truecolor")

# Render any Rich component (Table, Panel, Tree) to the memory console
mem_console.print(table)

# Export clean HTML for display in an ft.WebView or styled Markdown
html_output = mem_console.export_html(inline_styles=True)

# Or export plain text without ANSI codes for an ft.TextField
plain_text = mem_console.export_text(styles=False)
```

---

## 7. Summary & Architectural Recommendations

1. **Rich 15.0.0 Status:** Installed and verified in `Sherlock-V2\.venv`. Rich is robust and self-contained; it handles Windows console quirks natively without depending on `colorama`.
2. **Current Usage Pattern:** Both `user-scanner` and `phonsint` couple their scanning loops with CLI-specific `rich.progress.Progress` and stdout `print()` calls.
3. **Flet GUI Boundary:** In the GUI tier of Sherlock-V2, direct calls to `rich.print()`, `Progress`, and `colorama` must be replaced by event callbacks and native Flet widgets (`ft.ProgressBar`, `ft.ProgressRing`, `ft.ListView`, `ft.Card`).
4. **Execution Protocol:** Long-running scans must be awaited on Flet's event loop using `asyncio.create_task()` or delegated to worker threads with `asyncio.to_thread()` to ensure the UI remains smooth, responsive, and free of stream pollution.
