# Dependency Reference: Small Transitive Dependencies Cluster

This reference document provides an architectural, code-level, and operational study of the **13 small transitive dependencies** installed within the `Sherlock-V2` virtual environment (`/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages`).

The 13 analyzed packages are:
`msgpack`, `oauthlib`, `repath`, `six`, `h11`, `hpack`, `hyperframe`, `h2`, `certifi`, `mdurl`, `markdown-it-py`, `typing-extensions`, `idna`.

None of these packages are declared as direct dependencies in `Sherlock-V2/pyproject.toml`, nor are they directly imported by `Sherlock-V2` source code. Instead, they form foundational substrate layers brought in transitively by four primary dependencies: `flet`, `httpx` (via `httpcore`), `rich`, and `anyio`.

All citations throughout this document reference verified file locations and line numbers in `Sherlock-V2/.venv/Lib/site-packages` and the project workspace.

---

## 1. Cluster Overview & Dependency Graph

### 1.1 Ingress Vector Summary

The 13 transitive dependencies enter `Sherlock-V2` through four distinct functional vectors:

```
Sherlock-V2 (pyproject.toml)
│
├── flet (1.0.4) & flet-ads (1.0.4)
│   ├── msgpack (1.2.3)                     [Serialization: Dart/Python RPC bridge]
│   ├── oauthlib (4.0.0)                    [Networking/Auth: Page OAuth login flows]
│   └── repath (0.9.0)                      [Compat/Routing: Express-style route matcher]
│       └── six (1.17.0)                    [Compat: Python 2/3 compatibility bridge]
│
├── user-scanner (1.5.2.3) & phonsint (0.1.0)
│   ├── httpx[http2] (0.28.1)
│   │   ├── certifi (2026.10.18)            [TLS/HTTP: Mozilla Root CA bundle]
│   │   ├── idna (3.20)                     [TLS/HTTP: Internationalized domain names]
│   │   ├── httpcore (1.0.9)
│   │   │   ├── h11 (0.16.0)                [TLS/HTTP: Sans-I/O HTTP/1.1 state machine]
│   │   │   └── certifi (2026.10.18)
│   │   ├── h2 (4.4.1)                      [TLS/HTTP: Sans-I/O HTTP/2 state machine]
│   │   │   ├── hpack (4.2.0)               [TLS/HTTP: HPACK header compression RFC 7541]
│   │   │   └── hyperframe (6.1.0)          [TLS/HTTP: HTTP/2 binary framing RFC 7540/9113]
│   │   └── anyio (4.15.1)
│   │       ├── idna (3.20)
│   │       └── typing-extensions (4.16.0)  [Compat/Typing: Backported PEP typing constructs]
│   │
│   ├── curl-cffi (0.16.3)
│   │   └── certifi (2026.10.18)
│   │
│   └── rich (15.0.0)
│       └── markdown-it-py (4.2.0)          [Markup: CommonMark markdown parser]
│           └── mdurl (0.1.2)               [Markup: URL parsing and sanitization for markdown]
```

### 1.2 Direct vs Transitive Usage Audit

| Check Location | Target Packages Referenced | Status |
|---|---|---|
| `Sherlock-V2/pyproject.toml:7-12` | `flet`, `flet-ads`, `phonsint`, `user-scanner` | **No direct declarations** of the 13 transitive packages |
| `Sherlock-V2/src/sherlock_v2/__init__.py:1-3` | Main entry point stub (`print("Hello from sherlock-v2!")`) | **Zero direct imports** of any target package |
| `Sherlock-V2/uv.lock` | All 13 packages locked with exact hashes and wheel URLs | **Transitive resolution only** |

---

## 2. Functional Group 1: TLS & HTTP Networking Stack

The networking group constitutes the largest subset of the cluster (7 of 13 packages). It implements the transport security, host resolution, protocol state machines, framing, and authentication protocols that underpin `httpx`, `httpcore`, `curl-cffi`, and `flet`.

```
               ┌───────────────┐
               │    certifi    │  (Mozilla Root CA PEM Bundle)
               └───────┬───────┘
                       │ (TLS Context Verification)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                          httpx / httpcore                   │
├──────────────────────────────┬──────────────────────────────┤
│      HTTP/1.1 Wire Flow      │      HTTP/2 Multiplexing     │
├──────────────────────────────┼──────────────────────────────┤
│         ┌──────────┐         │         ┌──────────┐         │
│         │   h11    │         │         │    h2    │         │
│         └──────────┘         │         └────┬─────┘         │
│     (Sans-I/O HTTP/1.1       │     (Sans-I/O HTTP/2         │
│       State Machine)         │       State Machine)         │
│                              │        ┌─────┴─────┐         │
│                              │        ▼           ▼         │
│                              │   ┌─────────┐ ┌────────────┐ │
│                              │   │  hpack  │ │ hyperframe │ │
│                              │   └─────────┘ └────────────┘ │
│                              │  (RFC 7541)   (RFC 7540/9113)│
└──────────────────────────────┴──────────────────────────────┘
        ▲                                              ▲
        │ Host Normalization (Punycode/UTS#46)         │ Auth Handshake
        │                                              │
 ┌──────────────┐                             ┌────────────────┐
 │     idna     │                             │    oauthlib    │
 └──────────────┘                             └────────────────┘
```

---

### 2.1 certifi (Version: 2026.10.18)

- **Package Identity**: `certifi`
- **Installed Version**: `2026.10.18`
- **Version Declarations**:
  - `certifi/__init__.py:4`: `__version__ = "2026.10.18"`
  - `certifi-2026.10.18.dist-info/METADATA:3`: `Version: 2026.10.18`
- **License**: Mozilla Public License 2.0 (`MPL-2.0`)
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/certifi`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`certifi` provides Mozilla's carefully curated collection of Root Certificate Authorities (CA) packaged as an immutable PEM file (`cacert.pem`). Standard Python wheels on Windows, macOS, and Linux often lack access to native operating system trust stores or encounter stale certificates. `certifi` provides an authoritative, regularly updated baseline for TLS certificate validation.

#### Consumer Citations
1. **`httpcore` SSL Context Builder** (`httpcore/_ssl.py:1-9`):
   ```python
   # httpcore/_ssl.py:3, 6-9
   import certifi

   def default_ssl_context() -> ssl.SSLContext:
       context = ssl.create_default_context()
       context.load_verify_locations(certifi.where())
       return context
   ```
2. **`httpx` Default Verification** (`httpx/_config.py:31, 39-40`):
   ```python
   # httpx/_config.py:31, 40
   import certifi
   ...
   ctx = ssl.create_default_context(cafile=certifi.where())
   ```
3. **`curl-cffi` Native Curl CA Fallback** (`curl_cffi/curl.py:15, 22-26`):
   ```python
   # curl_cffi/curl.py:15
   import certifi
   # Lines 22-26 resolve CA file path falling back to certifi when SSL_CERT_FILE / CURL_CA_BUNDLE are unset
   ```

---

### 2.2 idna (Version: 3.20)

- **Package Identity**: `idna`
- **Installed Version**: `3.20`
- **Version Declarations**:
  - `idna/package_data.py:1`: `__version__ = "3.20"`
  - `idna/__init__.py:21-27`: Exposes `__version__` and `unicode_version` (`idnadata.py:3`)
  - `idna-3.20.dist-info/METADATA:3`: `Version: 3.20`
- **License**: BSD-3-Clause
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/idna`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
Implements Internationalized Domain Names in Applications (IDNA) according to RFC 5891 and Unicode Technical Standard #46 (UTS #46). It transforms non-ASCII internationalized hostnames (e.g., Unicode characters in international OSINT targets) into ASCII-Compatible Encoding (ACE) using Punycode (`xn--...`), ensuring safe inclusion in TLS Server Name Indication (SNI) extensions and HTTP `Host` headers.

#### Consumer Citations
1. **`httpx` Host Normalization** (`httpx/_urlparse.py:25, 388-392`):
   ```python
   # httpx/_urlparse.py:25, 390-391
   import idna
   ...
   try:
       return idna.encode(host.lower()).decode("ascii")
   except idna.IDNAError:
       raise InvalidURL(f"Invalid domain name: {host!r}")
   ```
2. **`httpx` High-Level URL Parser** (`httpx/_urls.py:6`):
   ```python
   import idna
   ```
3. **`anyio` Asynchronous Socket Host Encoding** (`anyio/_core/_sockets.py:64-69`):
   ```python
   # anyio/_core/_sockets.py:64-68
   try:
       return host.encode("ascii")
   except UnicodeEncodeError:
       import idna
       return idna.encode(host, uts46=True)
   ```

---

### 2.3 h11 (Version: 0.16.0)

- **Package Identity**: `h11`
- **Installed Version**: `0.16.0`
- **Version Declarations**:
  - `h11/_version.py:16`: `__version__ = "0.16.0"`
  - `h11/__init__.py:33-35`: `from h11._version import __version__; PRODUCT_ID = "python-h11/" + __version__`
  - `h11-0.16.0.dist-info/METADATA:3`: `Version: 0.16.0`
- **License**: MIT
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/h11`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`h11` is a pure-Python, **sans-I/O** HTTP/1.1 protocol state machine. It contains zero socket calls, zero system calls, and zero thread or asynchronous runtime primitives. It maintains an internal finite state machine (`h11._state.ConnectionState`) tracking client/server states (`IDLE`, `SEND_BODY`, `DONE`, `MUST_CLOSE`, `CLOSED`). Callers feed incoming network bytes via `conn.receive_data(data)` and retrieve typed high-level events (`Request`, `Response`, `Data`, `EndOfMessage`, `InformationalResponse`), or generate outbound bytes via `conn.send(event)`.

#### Consumer Citations
1. **`httpcore` Synchronous HTTP/1.1 Connection** (`httpcore/_sync/http11.py:10, 29-33, 60-63`):
   ```python
   # httpcore/_sync/http11.py:10
   import h11

   # httpcore/_sync/http11.py:60-63
   self._h11_state = h11.Connection(
       our_role=h11.CLIENT,
       max_incomplete_event_size=self.MAX_INCOMPLETE_EVENT_SIZE,
   )
   ```
2. **`httpcore` Asynchronous HTTP/1.1 Connection** (`httpcore/_async/http11.py:10, 60-63`):
   ```python
   # httpcore/_async/http11.py:10
   import h11
   self._h11_state = h11.Connection(
       our_role=h11.CLIENT,
       max_incomplete_event_size=self.MAX_INCOMPLETE_EVENT_SIZE,
   )
   ```

---

### 2.4 h2 (Version: 4.4.1)

- **Package Identity**: `h2`
- **Installed Version**: `4.4.1`
- **Version Declarations**:
  - `h2/__init__.py:6`: `__version__ = "4.4.1"`
  - `h2-4.4.1.dist-info/METADATA:3`: `Version: 4.4.1`
- **License**: MIT
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/h2`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`h2` is a pure-Python, **sans-I/O** implementation of the HTTP/2 state machine (RFC 7540 / RFC 9113). It orchestrates stream multiplexing, priority trees, flow control windows (connection-level and stream-level via `h2.windows.WindowManager`), server push promises, and settings negotiation. Incoming network chunks are processed via `conn.receive_data(data)`, which yields high-level semantic events (`ResponseReceived`, `DataReceived`, `StreamEnded`, `SettingsAcknowledged`, `RemoteSettingsChanged`), and outgoing data is generated via `conn.data_to_send()`.

#### Consumer Citations
1. **`httpcore` Synchronous HTTP/2 Connection** (`httpcore/_sync/http2.py:9-13, 65-72`):
   ```python
   # httpcore/_sync/http2.py:9-13
   import h2.config
   import h2.connection
   import h2.events
   import h2.exceptions
   import h2.settings

   config = h2.config.H2Configuration(client_side=True)
   self._h2_state = h2.connection.H2Connection(config=config)
   ```
2. **`httpcore` Asynchronous HTTP/2 Connection** (`httpcore/_async/http2.py:9-13`):
   Identical import and configuration pattern wrapped in `AsyncNetworkStream`.
3. **`httpx` HTTP/2 Availability Guard** (`httpx/_client.py:676-684, 1390-1397`):
   ```python
   # httpx/_client.py:678-682
   if http2:
       try:
           import h2  # noqa
       except ImportError:
           raise ImportError("Using http2=True, but the 'h2' package is not installed.")
   ```

---

### 2.5 hpack (Version: 4.2.0)

- **Package Identity**: `hpack`
- **Installed Version**: `4.2.0`
- **Version Declarations**:
  - `hpack/__init__.py:23`: `__version__ = "4.2.0"`
  - `hpack-4.2.0.dist-info/METADATA:3`: `Version: 4.2.0`
- **License**: MIT
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/hpack`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`hpack` implements RFC 7541 (HPACK: Header Compression for HTTP/2). Because HTTP/2 multiplexes hundreds of requests over a single TCP stream, uncompressed headers would create severe bandwidth overhead and vulnerability to CRIME/BREACH-style compression leaks. `hpack` maintains:
1. **Static Table**: 61 predefined indexed header name/value pairs (`hpack/table.py:18-81`).
2. **Dynamic Table**: FIFO sliding window for session-specific headers (`hpack/table.py:84-150`).
3. **Canonical Huffman Coding**: Tree-based bit packing for header literals (`hpack/huffman.py:10-85`).

#### Consumer Citations
1. **`h2` Connection Header Decoders & Encoders** (`h2/connection.py:14, 120-130`):
   ```python
   # h2/connection.py:14
   from hpack.hpack import Decoder, Encoder

   self.decoder = Decoder()
   self.encoder = Encoder()
   ```
2. **`h2` Stream Header Tuples** (`h2/stream.py:12, 51`):
   ```python
   from hpack import HeaderTuple
   from hpack.hpack import Encoder
   ```

---

### 2.6 hyperframe (Version: 6.1.0)

- **Package Identity**: `hyperframe`
- **Installed Version**: `6.1.0`
- **Version Declarations**:
  - `hyperframe/__init__.py:6`: `__version__ = "6.1.0"`
  - `hyperframe-6.1.0.dist-info/METADATA:3`: `Version: 6.1.0`
- **License**: MIT
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/hyperframe`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`hyperframe` handles the lowest level of the HTTP/2 wire protocol: **binary framing**. It defines the 9-byte frame header (`length: 24-bit`, `type: 8-bit`, `flags: 8-bit`, `stream_id: 31-bit`) and serializes/deserializes frame payloads for all RFC 7540 / RFC 9113 types:
- `DataFrame` (`type = 0x0`)
- `HeadersFrame` (`type = 0x1`)
- `PriorityFrame` (`type = 0x2`)
- `RstStreamFrame` (`type = 0x3`)
- `SettingsFrame` (`type = 0x4`)
- `PushPromiseFrame` (`type = 0x5`)
- `PingFrame` (`type = 0x6`)
- `GoAwayFrame` (`type = 0x7`)
- `WindowUpdateFrame` (`type = 0x8`)
- `ContinuationFrame` (`type = 0x9`)
- `AltSvcFrame` (`type = 0xA`)

#### Consumer Citations
1. **`h2` Frame Buffer Parser** (`h2/frame_buffer.py:12-13, 40-55`):
   ```python
   # h2/frame_buffer.py:12-13
   from hyperframe.exceptions import InvalidDataError, InvalidFrameError
   from hyperframe.frame import ContinuationFrame, Frame, HeadersFrame, PushPromiseFrame

   frame, length = Frame.parse_frame_header(self.data[:9])
   frame.parse_body(memoryview(self.data[9:9+length]))
   ```
2. **`h2` Connection Framing Handling** (`h2/connection.py:15-20`):
   ```python
   from hyperframe.exceptions import InvalidPaddingError
   from hyperframe.frame import (
       AltSvcFrame, ContinuationFrame, DataFrame, Frame, GoAwayFrame,
       HeadersFrame, PingFrame, PriorityFrame, PushPromiseFrame,
       RstStreamFrame, SettingsFrame, WindowUpdateFrame,
   )
   ```
3. **`h2` Stream and Event Generation** (`h2/events.py:21`, `h2/stream.py:13`, `h2/settings.py:15`).

---

### 2.7 oauthlib (Version: 4.0.0)

- **Package Identity**: `oauthlib`
- **Installed Version**: `4.0.0`
- **Version Declarations**:
  - `oauthlib/__init__.py:15`: `__version__ = '4.0.0'`
  - `oauthlib-4.0.0.dist-info/METADATA:3`: `Version: 4.0.0`
- **License**: BSD-3-Clause
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/oauthlib`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`oauthlib` is a generic, spec-compliant sans-I/O implementation of OAuth 1.0 and OAuth 2.0 authorization logic. It builds authorization request URLs, enforces CSRF state validation, generates PKCE code challenges/verifiers (`code_challenge`, `code_verifier`), formats URL-encoded token request payloads, and parses OAuth token responses.

#### Consumer Citations
Used exclusively by Flet's authentication subsystem to empower GUI login flows (e.g., GitHub, Google, Azure, Auth0 logins in `flet.Page`):
1. **OAuth Redirect URL Generation** (`flet/auth/authorization_service.py:93-106`):
   ```python
   # flet/auth/authorization_service.py:93, 96-105
   from oauthlib.oauth2 import WebApplicationClient

   client = WebApplicationClient(self.provider.client_id)
   authorization_url = client.prepare_request_uri(
       self.provider.authorization_endpoint,
       self.provider.redirect_url,
       scope=self.scope,
       state=self.state,
       code_challenge=self.provider.code_challenge,
       code_challenge_method=self.provider.code_challenge_method,
       **self.provider.authorization_params,
   )
   ```
2. **Token Exchange Body Formatting** (`flet/auth/authorization_service.py:120-129`):
   ```python
   # flet/auth/authorization_service.py:120, 122-129
   from oauthlib.oauth2 import WebApplicationClient

   client = WebApplicationClient(self.provider.client_id)
   data = client.prepare_request_body(
       code=code,
       redirect_uri=self.provider.redirect_url,
       client_secret=self.provider.client_secret,
       include_client_id=True,
       code_verifier=self.provider.code_verifier,
   )
   ```
3. **Token Response Parsing** (`flet/auth/authorization_service.py:138-140, 168-174, 208`):
   ```python
   # flet/auth/authorization_service.py:138-140
   client = WebApplicationClient(self.provider.client_id)
   t = client.parse_request_body_response(resp.text)
   self.__token = self.__convert_token(t)
   ```

---

## 3. Functional Group 2: Binary Serialization

---

### 3.1 msgpack (Version: 1.2.3)

- **Package Identity**: `msgpack`
- **Installed Version**: `1.2.3`
- **Version Declarations**:
  - `msgpack/__init__.py:7`: `version = (1, 2, 3)`
  - `msgpack/__init__.py:8`: `__version__ = "1.2.3"`
  - `msgpack-1.2.3.dist-info/METADATA:3`: `Version: 1.2.3`
- **License**: Apache-2.0
- **Distribution**: C-extension wheel (`cp314-win_amd64.pyd` installed, with `msgpack/fallback.py` pure-Python fallback)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/msgpack`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
MessagePack is an efficient binary serialization format that functions like binary JSON, but is significantly smaller and faster to serialize/deserialize. In `Sherlock-V2`, `msgpack` is the **core IPC/RPC transport format** between the Python process and the Flutter/Dart UI engine in `flet`.

Flet serializes all control trees, widget layout updates, state diffs, events, and asset metadata into MessagePack packets rather than JSON strings, drastically reducing memory pressure and transmission latency.

#### Wire Protocol Framing in Flet
Flet structures wire frames with a 1-byte opcode prefix:
- `[0x00][msgpack payload]`: Standard UI state mutation / control tree update.
- Custom Extension Types: Date/time instances, `flet.Duration`, and dataclasses are packed via custom hooks.

#### Consumer Citations
1. **Flet Protocol Encoder & Ext Hooks** (`flet/messaging/protocol.py:6, 26-48`):
   ```python
   # flet/messaging/protocol.py:6, 26-33
   import msgpack

   def configure_encode_object_for_msgpack(control_cls):
       """
       Builds an object encoder callback for Flet's MessagePack transport.
       The returned function is passed to msgpack.packb(..., default=...) and handles
       protocol-specific serialization rules for dataclasses, enums, date/time objects,
       Duration, and extension values exchanged with Dart.
       """
   ```
2. **Dart Bridge Server (Desktop/Mobile IPC)** (`flet/messaging/flet_dart_bridge_server.py:33, 129-130, 225-231`):
   ```python
   # flet/messaging/flet_dart_bridge_server.py:33, 129-130
   import msgpack
   msg = msgpack.unpackb(packet[1:], ext_hook=decode_ext_from_msgpack)

   # Lines 229-231
   body = msgpack.packb(
       message, default=configure_encode_object_for_msgpack(BaseControl)
   )
   ```
3. **Socket Server (Out-of-Process / Web UI)** (`flet/messaging/flet_socket_server.py:13, 287, 438-440`):
   ```python
   # Wire format: [length:u32 LE][0x00][msgpack body]
   msg = msgpack.unpackb(packet[1:], ext_hook=decode_ext_from_msgpack)
   body = msgpack.packb(message, default=configure_encode_object_for_msgpack(BaseControl))
   ```
4. **Pyodide / WebAssembly Connection** (`flet/messaging/pyodide_connection.py:9, 92, 206-208`).

---

## 4. Functional Group 3: Markup & Text Rendering

---

### 4.1 markdown-it-py (Version: 4.2.0)

- **Package Identity**: `markdown-it-py`
- **Installed Version**: `4.2.0`
- **Version Declarations**:
  - `markdown_it/__init__.py:4`: `__version__ = "4.2.0"`
  - `markdown_it_py-4.2.0.dist-info/METADATA:3`: `Version: 4.2.0`
- **License**: MIT (`markdown_it_py-4.2.0.dist-info/licenses/LICENSE`)
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/markdown_it`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`markdown-it-py` is a 100% CommonMark-compliant Markdown parser ported from JavaScript's `markdown-it`. It parses Markdown documents into a stream of structured, typed tokens (`markdown_it.token.Token`) with nested syntactical levels, block rules (headings, lists, tables, code fences), and inline rules (links, emphasis, code spans).

#### Consumer Citations
Used by `rich` to render rich formatted Markdown in terminal interfaces (such as `user-scanner` and `phonsint` CLI scans):
1. **`rich.markdown` Integration** (`rich/markdown.py:7, 10, 80-95`):
   ```python
   # rich/markdown.py:7, 10
   from markdown_it import MarkdownIt
   from markdown_it.token import Token

   class Markdown:
       def __init__(self, markup: str, code_theme: str = "monokai", ...):
           parser = MarkdownIt().enable("strikethrough").enable("table")
           self.parsed = parser.parse(markup)
   ```

---

### 4.2 mdurl (Version: 0.1.2)

- **Package Identity**: `mdurl`
- **Installed Version**: `0.1.2`
- **Version Declarations**:
  - `mdurl/__init__.py:12`: `__version__ = "0.1.2"`
  - `mdurl-0.1.2.dist-info/METADATA:3`: `Version: 0.1.2`
- **License**: MIT (`mdurl-0.1.2.dist-info/LICENSE`)
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/mdurl`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`mdurl` is a specialized, zero-dependency URL utility library extracted from `markdown-it`. It provides RFC 3986 URL parsing, percent-encoding, percent-decoding, and normalization. Markdown links often contain unescaped characters, malformed entities, or invalid percent sequences; `mdurl` cleanses and normalizes URLs without invoking bulky networking libraries.

#### Consumer Citations
1. **`markdown_it` URL Normalization** (`markdown_it/common/normalize_url.py:8, 11-20`):
   ```python
   # markdown_it/common/normalize_url.py:8, 11-14
   import mdurl

   def normalize_url(url: str) -> str:
       """Normalize destination for links and images."""
       return mdurl.encode(mdurl.decode(url))
   ```

---

## 5. Functional Group 4: Compatibility, Routing & Language Extensions

---

### 5.1 typing-extensions (Version: 4.16.0)

- **Package Identity**: `typing-extensions`
- **Installed Version**: `4.16.0`
- **Version Declarations**:
  - `typing_extensions-4.16.0.dist-info/METADATA:3`: `Version: 4.16.0`
- **License**: PSF-2.0 (`typing_extensions-4.16.0.dist-info/licenses/LICENSE`)
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/typing_extensions.py`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`typing-extensions` backports typing features, generic syntax, and typing PEPs across Python releases. Even on modern Python runtimes like Python 3.14 (the interpreter configured for this workspace via `.python-version: 3.14`), libraries targeting broad compatibility (such as `anyio 4.15.1`) rely on `typing_extensions` for constructs like `Self`, `TypeVarTuple`, `Unpack`, `sentinel`, and complex type narrowing.

#### Consumer Citations
1. **`anyio` Thread and Process Task Pools** (`anyio/from_thread.py:48`, `anyio/to_process.py:31`, `anyio/to_thread.py:21`):
   ```python
   # anyio/from_thread.py:48
   from typing_extensions import Self, TypeVarTuple, Unpack
   ```
2. **`anyio` Abstract Task and Resource Interfaces** (`anyio/abc/_eventloop.py:31`, `anyio/abc/_resources.py:11`, `anyio/abc/_tasks.py:13, 18`):
   ```python
   # anyio/abc/_tasks.py:13, 18
   from typing_extensions import TypeVar, TypeVarTuple, Unpack
   ```
3. Total consumer citations across `anyio`: **32 separate import occurrences**.

---

### 5.2 repath (Version: 0.9.0)

- **Package Identity**: `repath`
- **Installed Version**: `0.9.0`
- **Version Declarations**:
  - `repath-0.9.0.dist-info/METADATA:3`: `Version: 0.9.0`
- **License**: MIT
- **Distribution**: Pure Python wheel (`py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/repath.py`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`repath` is a Python port of the JavaScript `path-to-regexp` library used by ExpressJS. It compiles expressive route template strings containing named parameters, optional suffixes, wildcards, and splats (e.g. `"/user/:id"`, `"/targets/:username?"`, `"/scan/*path"`) into native Python regular expressions with named capturing groups (`re.compile(...)`).

#### Consumer Citations
Used by `flet` to drive both component-level declarative routing and page-level template routes:
1. **`flet.TemplateRoute` Parameter Extractor** (`flet/controls/template_route.py:3, 44-51`):
   ```python
   # flet/controls/template_route.py:3, 44-51
   import repath

   def match(self, route_template: str) -> bool:
       pattern = repath.pattern(route_template)
       match = re.match(pattern, self.route)
       if match:
           self.__last_params = match.groupdict()
           for k, v in self.__last_params.items():
               setattr(self, k, v)
           return True
       return False
   ```
2. **`flet` React Router-like Declarative Router** (`flet/components/router.py:16, 191, 228, 265, 287, 302`):
   ```python
   # flet/components/router.py:16, 191, 228
   import repath

   pattern = repath.pattern(full_path)
   prefix_pattern = repath.pattern(full_path, end=False)
   ```

---

### 5.3 six (Version: 1.17.0)

- **Package Identity**: `six`
- **Installed Version**: `1.17.0`
- **Version Declarations**:
  - `six.py:32`: `__version__ = "1.17.0"`
  - `six-1.17.0.dist-info/METADATA:3`: `Version: 1.17.0`
- **License**: MIT
- **Distribution**: Pure Python universal wheel (`py2.py3-none-any`)
- **Location**: `/home/maikel/.zcode/workspace/default/Sherlock-V2/.venv/Lib/site-packages/six.py`
- **Direct Use by Sherlock-V2**: **No**.

#### Role & Mechanism
`six` is the classic Python 2 and Python 3 compatibility library. While modern Python codebases targeting `>=3.10` have eliminated `six`, older utility packages that have remained stable and unedited for years still depend on it. In this environment, `six` exists solely because `repath 0.9.0` imports it for string type predicates and urllib imports.

#### Consumer Citations
1. **`repath.py` Compatibility Bindings** (`repath.py:3-4, 144, 174, 185, 204, 207`):
   ```python
   # repath.py:3-4
   import six
   from six.moves.urllib import parse as urllib

   # repath.py:144, 174
   if isinstance(token, six.string_types):
       val = six.text_type(val)
   ```

---

## 6. Comprehensive Audit Matrix

| Package | Version | Group | Role Summary | Upstream Parent | Direct Use | Python Req | Wheel Arch | License |
|---|---|---|---|---|---|---|---|---|
| **`certifi`** | `2026.10.18` | TLS/HTTP | Mozilla Root CA PEM trust bundle | `httpx`, `httpcore`, `curl-cffi` | **No** | `>=3.7` | `py3-none-any` | MPL-2.0 |
| **`idna`** | `3.20` | TLS/HTTP | IDNA RFC 5891 / UTS #46 Punycode host encoding | `httpx`, `anyio` | **No** | `>=3.9` | `py3-none-any` | BSD-3-Clause |
| **`h11`** | `0.16.0` | TLS/HTTP | Sans-I/O HTTP/1.1 protocol state machine | `httpcore` (`httpx`) | **No** | `>=3.8` | `py3-none-any` | MIT |
| **`h2`** | `4.4.1` | TLS/HTTP | Sans-I/O HTTP/2 protocol state machine | `httpx[http2]`, `httpcore` | **No** | `>=3.10` | `py3-none-any` | MIT |
| **`hpack`** | `4.2.0` | TLS/HTTP | RFC 7541 HPACK header compression for HTTP/2 | `h2` | **No** | `>=3.10` | `py3-none-any` | MIT |
| **`hyperframe`**| `6.1.0` | TLS/HTTP | RFC 7540 / 9113 HTTP/2 binary frame serializer | `h2` | **No** | `>=3.9` | `py3-none-any` | MIT |
| **`oauthlib`** | `4.0.0` | TLS/HTTP | Sans-I/O OAuth 1.0 & 2.0 authorization logic | `flet` | **No** | `>=3.9` | `py3-none-any` | BSD-3-Clause |
| **`msgpack`** | `1.2.3` | Serialization | High-performance binary serializer (Dart-Python RPC) | `flet` | **No** | `>=3.10` | `cp314-win_amd64` (C ext) | Apache-2.0 |
| **`markdown-it-py`** | `4.2.0` | Markup | CommonMark-compliant Markdown parser token stream | `rich` | **No** | `>=3.10` | `py3-none-any` | MIT |
| **`mdurl`** | `0.1.2` | Markup | RFC 3986 Markdown URL normalizer and encoder | `markdown-it-py` | **No** | `>=3.7` | `py3-none-any` | MIT |
| **`typing-extensions`** | `4.16.0` | Compat | Backported typing hints and typing PEPs | `anyio`, `flet` | **No** | `>=3.9` | `py3-none-any` | PSF-2.0 |
| **`repath`** | `0.9.0` | Compat | ExpressJS route pattern to regex compiler | `flet` | **No** | Any | `py3-none-any` | MIT |
| **`six`** | `1.17.0` | Compat | Legacy Python 2/3 compatibility bridge | `repath` | **No** | `>=2.7, !=3.0-3.2` | `py2.py3-none-any` | MIT |

---

## 7. Runtime Architecture & Mobile / Desktop Implications

### 7.1 Sans-I/O Architectural Cluster
A striking architectural feature of this cluster is that **5 of the 13 packages** (`h11`, `h2`, `hpack`, `hyperframe`, and `oauthlib`) adhere strictly to the **sans-I/O pattern**:
- They contain **no network I/O**, **no filesystem writes**, and **no operating system threads**.
- This separation of protocol state logic from socket operations guarantees deterministic, testable protocol compliance and makes them seamlessly portable between synchronous code (`httpcore._sync`), asynchronous event loops (`asyncio`, `anyio`, `trio`), and custom embedded runtimes.

### 7.2 Binary vs Pure Python Execution
- **12 of the 13 packages** are pure Python (`Root-Is-Purelib: true`, `py3-none-any` wheels).
- Only **`msgpack`** compiles a native C-extension (`_cmsgpack.cp314-win_amd64.pyd`). However, `msgpack` ships with a complete, fully tested pure-Python fallback (`msgpack/fallback.py:1-1050`), meaning that in constrained environments where native compilation is prohibited (e.g., Pyodide / WebAssembly, or restricted iOS App Store sandboxes without dynamic linking), `msgpack` automatically falls back to pure Python without breaking Flet's UI bridge.

### 7.3 Mobile Deployment Considerations (Flet on Android / iOS)
When packaging `Sherlock-V2` for Android or iOS with Flet:
1. **CA Certificates (`certifi`)**: Mobile OS sandboxes often restrict file paths. `certifi.where()` provides a stable path inside the packaged app bundle, ensuring consistent SSL handshakes across varied mobile Android/iOS versions.
2. **Domain Resolution (`idna`)**: Required when scanning internationalized usernames or querying regional platforms with non-ASCII characters.
3. **HTTP/2 Transport (`h2`, `hpack`, `hyperframe`)**: Mobile networks benefit heavily from HTTP/2 multiplexing (reducing TCP handshake latency over cellular connections).
4. **Binary Serialization (`msgpack`)**: Ensures that high-frequency UI events between the Flutter engine and Python do not saturate the mobile device CPU.
5. **Legacy Footprint (`six`, `repath`)**: While `repath` and `six` are older packages, their small footprint (<300 lines for `repath`, ~1000 lines for `six`) adds negligible overhead to the mobile package size.
