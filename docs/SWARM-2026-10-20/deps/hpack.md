# Dependency Audit: hpack 4.2.0 (Sherlock V3)

Repo root: `/home/maikel/.zcode/workspace/default/Sherlock-V3` · Venv (source of truth): `.venv\Lib\site-packages\`

---

## 1. Installed verification

| Fact | Value | Evidence |
|---|---|---|
| Version | `4.2.0` | `hpack\__init__.py:23` (`__version__ = "4.2.0"`); `hpack-4.2.0.dist-info\METADATA:3` |
| Summary | "Pure-Python HPACK header encoding" | `hpack-4.2.0.dist-info\METADATA:4` |
| Packaging | Pure Python, `Root-Is-Purelib: true`, 9 modules | `hpack-4.2.0.dist-info\WHEEL`, `RECORD:8-16` |
| Runtime deps | None (stdlib only) | `hpack-4.2.0.dist-info\METADATA` (no `Requires-Dist`) |
| Installed by | `h2` 4.4.1 | `h2-4.4.1.dist-info\METADATA:27` → `Requires-Dist: hpack<5,>=4.2` |
| Chain | `httpx[http2]` → `h2` → `hpack` | `httpx-0.28.1.dist-info\METADATA:38-39` (`http2` extra → `h2<5,>=3`) |

Public API (`hpack\__init__.py:6-8`): `Decoder`, `Encoder`, `HeaderTuple`,
`NeverIndexedHeaderTuple`, `HPACKError`, `HPACKDecodingError`, `InvalidTableIndex(Error)`,
`InvalidTableSizeError`, `OversizedHeaderListError`.

**Static table — PRESENT.** `hpack\table.py:26` `class HeaderTable`; `:42` `STATIC_TABLE = (`;
`:106` `STATIC_TABLE_LENGTH`; `:108`/`:237` `STATIC_TABLE_MAPPING`. Runtime: **61 entries**
(RFC 7541 Appendix A), `DEFAULT_SIZE = 4096` (`table.py:38-39`); dynamic-index arithmetic
`table.py:131-134, 177, 185`.

**Huffman codec — PRESENT.** `hpack\huffman.py:8` `class HuffmanEncoder` (`:18` `encode()`,
bit-packing + EOS padding); decoder `hpack\huffman_table.py:78` `def decode_huffman(...)` —
168 KB port of nghttp2's `nghttp2_hd_huffman_data.c` (`huffman_table.py:1-12`); constants in
`huffman_constants.py`, imported at `hpack.py:10-11`. Integer/string primitives:
`hpack.py:50` `encode_integer`, `hpack.py:81` `decode_integer`.

## 2. Consumer

**Sole importer in the venv: the `h2` package.** Grep for `from hpack`/`import hpack` across all
of `site-packages` returns h2 hits only — `connection.py:13` (`hpack.exceptions`), `:14`
(`hpack.hpack Decoder, Encoder`), `:71` (`hpack.struct`, TYPE_CHECKING); `events.py:20`
(`hpack.struct`, TYPE_CHECKING); `stream.py:12` (`from hpack import HeaderTuple`), `:51-52`
(`hpack.hpack Encoder`, `hpack.struct`, TYPE_CHECKING); `utilities.py:12` (`hpack.struct
HeaderTuple, NeverIndexedHeaderTuple`), `:19` (`hpack.struct`, TYPE_CHECKING).

> Correction to the brief: the importing set is **not** limited to `h2/connection.py` and
> `h2/stream.py` — `h2/events.py` and `h2/utilities.py` import from `hpack` too. `h2` remains
> the only consumer package.

**Wiring.** `h2\connection.py:330-331` creates `self.encoder = Encoder()` /
`self.decoder = Decoder()` per HTTP/2 connection; `h2\stream.py:860, 916, 1287` type the
stream-level encoder; `h2\connection.py:2096` `_decode_headers(decoder, ...)` decodes HEADERS.

**App never imports it.** Repo-wide grep (excluding `.venv`) for `import hpack|from hpack|
import h2\b|from h2\b` → **zero matches**. Only httpx touchpoint is `src\services\http_client.py:17`
(`import httpx`), whose clients are built with `http2=True` (`http_client.py:58, 61, 67, 74`).
`pyproject.toml:7-12` declares only `flet`, `flet-ads`, `user-scanner`, `phonsint`.

## 3. Role

HPACK (RFC 7541) header compression for HTTP/2. `Encoder`/`Decoder` (`hpack.py:162, 418`)
implement the integer/string literal codings (`hpack.py:50, 81`), the static + dynamic header
table (`table.py`), and Huffman-coded literals (`huffman.py`, `huffman_table.py`) — the two
mechanisms that make HTTP/2 headers cheap on the wire.

For Sherlock V3: the shared pooled `httpx.AsyncClient` in `src\services\http_client.py` is
created with `http2=True`, so `httpx` → `httpcore` → `h2` → `hpack` is the multiplexed HTTP/2
path. Every HEADERS frame on the app's engine requests/responses is HPACK-compressed here —
one encoder/decoder pair per connection, with the per-connection dynamic table deduplicating
repeated header bytes across the multiplexed streams `user-scanner`'s ~5,200 site checks fan
out over. `hpack` is invisible to app code: it is the compression layer *under* HTTP/2.

## 4. Verdict

**N/A for direct use.** No app file imports `hpack`; it is not a declared dependency and
exposes no app-facing surface. Nothing to wrap, pin, or document in app-facing docs.

**PERFECT as transitive.** Zero declared deps, pure Python, version-compatible with `h2`'s
`hpack<5,>=4.2` constraint, with static table and Huffman codec both fully present and
functional. Load-bearing for the `http2=True` path but entirely owned by `h2`.
**Action: none** — do not pin, vendor, or patch.
