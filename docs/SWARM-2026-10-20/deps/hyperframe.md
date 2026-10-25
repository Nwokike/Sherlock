# Dependency Audit: hyperframe

**Verdict: PERFECT as a transitive dependency / N/A for direct use.** Pure-Python HTTP/2 binary framing layer; the app never imports it and has no reason to.

## 1) Installed verification

- Version **6.1.0** — `hyperframe/__init__.py:6` (`__version__ = "6.1.0"`); dist-info `hyperframe-6.1.0.dist-info/` (METADATA:3 `Version: 6.1.0`).
- Self-described purpose, `hyperframe/__init__.py:2-3`: *"Provides a pure-Python HTTP/2 framing layer."*
- **Entire package is 5 files** (per `hyperframe-6.1.0.dist-info/RECORD`): `__init__.py`, `exceptions.py`, `flags.py`, `frame.py`, `py.typed`. No compiled extensions, no binary wheels, no subpackages — pure Python, MIT licensed, Cory Benfield (author) / Thomas Kriechbaumer (maintainer).
- **Sans-I/O / no network I/O.** It has no sockets and no transport: it only encodes and decodes HTTP/2 frame bytes. The wire format is fixed by `struct.Struct` layouts declared at `hyperframe/frame.py:33-39` (e.g. `>HBBBL` for the 9-byte frame header), with `FRAME_MAX_LEN = 2**14` (`frame.py:22`) and `FRAME_MAX_ALLOWED_LEN = 2**24 - 1` (`frame.py:25`).
- Surface is three files: `frame.py` (31,659 bytes, the bulk), `flags.py` (1,294 bytes), `exceptions.py` (1,516 bytes). `py.typed` is present, so it ships type hints.

## 2) Consumer — `h2` is the **sole** importer

- `grep -rn "hyperframe" --include=*.py` across all of `site-packages` returns hits in **`h2/` only** (plus hyperframe's own internal self-references). **No other installed package imports hyperframe.**
- h2's import sites:
  - `h2/connection.py:15-29` — imports `InvalidPaddingError` plus 13 frame classes: `AltSvcFrame, ContinuationFrame, DataFrame, ExtensionFrame, Frame, GoAwayFrame, HeadersFrame, PingFrame, PriorityFrame, PushPromiseFrame, RstStreamFrame, SettingsFrame, WindowUpdateFrame`.
  - `h2/frame_buffer.py:12-13` — `InvalidDataError, InvalidFrameError` + `ContinuationFrame, Frame, HeadersFrame, PushPromiseFrame` (the reassembly path).
  - `h2/stream.py:13` — `AltSvcFrame, ContinuationFrame, DataFrame, Frame, HeadersFrame, PushPromiseFrame, RstStreamFrame, WindowUpdateFrame`.
  - `h2/settings.py:15` — `SettingsFrame`.
  - `h2/events.py:21` — `Frame` under `TYPE_CHECKING` only (typing-only, not a runtime import).
  - `h2/connection.py:1796` — comment: *"hyperframe will take care of validating the window_increment."*
- Declared dependency: `h2-4.4.1.dist-info/METADATA:26` → `Requires-Dist: hyperframe<7,>=6.1`.
- **Full install chain into Sherlock-V3:** `pyproject.toml:8-11` declares `user-scanner>=1.5.2.3` and `phonsint>=0.1.0` → `user_scanner-1.5.2.3.dist-info/METADATA:10` and `phonsint-0.1.0.dist-info/METADATA:25` both require `httpx[http2]` → `httpx-0.28.1.dist-info/METADATA:39` (`h2<5,>=3; extra == 'http2'`) and `httpcore-1.0.9.dist-info/METADATA` (`h2<5,>=3; extra == 'http2'`, consumed at `httpcore/_async/http2.py:9-13`) → **h2 4.4.1** → **hyperframe 6.1.0**.
- **App usage: zero.** `grep -rn "hyperframe" --include=*.py --include=*.toml --include=*.txt` over the Sherlock-V3 tree (excluding `.venv`) → **0 hits**. It is never a direct dependency in `pyproject.toml:7-12`.

## 3) Role — HTTP/2 binary framing layer

hyperframe implements the **frame-level** half of RFC 7540 §4/§6, sitting directly under `h2` (which implements the *state machine*, HPACK is separate in `hpack`). It is the codec that turns HTTP/2 frames into bytes and back:

- **Base abstractions:** `Frame` (`frame.py:42`, with `type: int | None = None` at `frame.py:51`), plus the mixins `Padding` (`frame.py:197`) and `Priority` (`frame.py:237`).
- **Frame types available in `frame.py`** (class line → RFC type code):
  | Class | Line | `type` | RFC 7540 |
  |---|---|---|---|
  | `DataFrame` | `frame.py:278` | `0x0` (`:292`) | DATA |
  | `HeadersFrame` | `frame.py:697` | `0x1` (`:719`) | HEADERS |
  | `PriorityFrame` | `frame.py:334` | `0x2` (`:345`) | PRIORITY |
  | `RstStreamFrame` | `frame.py:364` | `0x3` (`:378`) | RST_STREAM |
  | `SettingsFrame` | `frame.py:408` | `0x4` (`:425`) | SETTINGS |
  | `PushPromiseFrame` | `frame.py:482` | `0x5` (`:495`) | PUSH_PROMISE |
  | `PingFrame` | `frame.py:543` | `0x6` (`:554`) | PING |
  | `GoAwayFrame` | `frame.py:585` | `0x7` (`:597`) | GOAWAY |
  | `WindowUpdateFrame` | `frame.py:645` | `0x8` (`:663`) | WINDOW_UPDATE |
  | `ContinuationFrame` | `frame.py:762` | `0x9` (`:777`) | CONTINUATION |
  | `AltSvcFrame` | `frame.py:798` | `0xA` (`:814`) | ALTSVC (RFC 7838) |
  | `ExtensionFrame` | `frame.py:854` | dynamic (`:874`) | generic extension frames |
- **Key API:** `Frame.explain` (`frame.py:89`) and `Frame.parse_frame_header` (`frame.py:106`) parse an incoming byte stream into a frame + consumed length; `Frame.serialize` (`frame.py:154`) / `serialize_body` (`frame.py:180`) produce the wire bytes; `Frame.parse_flags` (`frame.py:147`) decodes the flag byte. The `Padding`/`Priority` mixins supply the optional padding-length and priority fields for the frame types that carry them.
- **Error taxonomy** (`hyperframe/exceptions.py`), all deriving from `HyperframeError` (`:7`): `UnknownFrameError` (`:15`), `InvalidPaddingError` (`:36`), `InvalidFrameError` (`:45`), `InvalidDataError` (`:56`).
- **Flag handling** (`hyperframe/flags.py`): `Flag` NamedTuple (`:10`) and `Flags` MutableSet (`:15`) for the per-frame-type flag bits.

## 4) Verdict

**PERFECT as transitive / N/A for direct use.**

hyperframe is a single-purpose, pure-Python, sans-I/O codec that does exactly one job (HTTP/2 frame encode/decode) and does it behind a stable, typed API. It has exactly one consumer — `h2` — which is itself a transitive dependency of `httpx[http2]`, pulled in by the app's direct deps `user-scanner` and `phonsint`. Sherlock-V3 never imports it, and there is no app feature (it is a username/OSINT scanner making plain HTTPS calls) that would benefit from talking to HTTP/2 frames directly.

Action: **none.** Do not add it to `pyproject.toml`, do not import it in app code, do not add it to `[tool.flet.cleanup]` (it is required at runtime by `h2` whenever the `http2` extra of httpx is active). Version pinning and upgrades should be left to `h2`'s own constraint (`hyperframe<7,>=6.1`).
