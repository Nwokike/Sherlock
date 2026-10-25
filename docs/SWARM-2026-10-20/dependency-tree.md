# Sherlock V3 — Dependency Tree (post-cleanup, 2026-10-20)

Source of truth: `uv tree` + `importlib.metadata` against `.venv`
(Python 3.14.7). This replaces the pre-cleanup tree that included
`reportlab`/`pillow`/`svglib` and their transitives.

```
sherlock v2.3.0
├── flet v1.0.4
│   ├── httpx v0.28.1
│   │   ├── anyio v4.15.1
│   │   │   ├── idna v3.20
│   │   │   └── typing-extensions v4.16.0
│   │   ├── certifi v2026.10.18
│   │   ├── httpcore v1.0.9
│   │   │   ├── certifi v2026.10.18
│   │   │   └── h11 v0.16.0
│   │   └── idna v3.20
│   ├── msgpack v1.2.3
│   ├── oauthlib v4.0.0
│   └── repath v0.9.0
│       └── six v1.17.0
├── flet-ads v1.0.4
│   └── flet v1.0.4
├── phonsint v0.1.0
│   ├── colorama v0.4.6
│   ├── curl-cffi v0.16.3
│   │   ├── certifi v2026.10.18
│   │   └── cffi v2.1.1
│   │       └── pycparser v3.11
│   ├── httpx[http2] v0.28.1
│   │   ├── anyio v4.15.1
│   │   ├── certifi v2026.10.18
│   │   ├── httpcore v1.0.9
│   │   ├── idna v3.20
│   │   └── h2 v4.4.1 (extra: http2)
│   │       ├── hpack v4.2.0
│   │       └── hyperframe v6.1.0
│   ├── phonenumbers v9.0.41
│   └── rich v15.0.0
│       ├── markdown-it-py v4.2.0
│       │   └── mdurl v0.1.2
│       └── pygments v2.21.0
├── user-scanner v1.5.2.3
│   ├── colorama v0.4.6
│   ├── curl-cffi v0.16.3
│   ├── httpx[http2] v0.28.1
│   ├── rich v15.0.0
│   └── socksio v1.0.0
├── pytest v9.1.1 (group: dev)
│   ├── colorama v0.4.6
│   ├── iniconfig v2.3.1
│   ├── packaging v26.3
│   ├── pluggy v1.7.0
│   └── pygments v2.21.0
├── pytest-timeout v2.4.0 (group: dev)
│   └── pytest v9.1.1
└── ruff v0.17.1 (group: dev)
```

## Direct dependencies (4)
`flet`, `flet-ads`, `user-scanner`, `phonsint`.

## Full installed inventory (34 packages)
```
Pygments==2.21.0        markdown-it-py==4.2.0
anyio==4.15.1           mdurl==0.1.2
certifi==2026.10.18     msgpack==1.2.3
cffi==2.1.1             oauthlib==4.0.0
colorama==0.4.6         packaging==26.3
curl_cffi==0.16.3       phonenumbers==9.0.41
flet==1.0.4             phonsint==0.1.0
flet-ads==1.0.4         pluggy==1.7.0
h11==0.16.0             pycparser==3.11
h2==4.4.1               pytest==9.1.1
hpack==4.2.0            pytest-timeout==2.4.0
httpcore==1.0.9         repath==0.9.0
httpx==0.28.1           rich==15.0.0
hyperframe==6.1.0       ruff==0.17.1
idna==3.20              six==1.17.0
iniconfig==2.3.1        socksio==1.0.0
                        typing_extensions==4.16.0
                        user-scanner==1.5.2.3
```

## Removed by owner order (2026-10-20)
`reportlab`, `pillow`, `svglib` — and transitively: charset-normalizer,
click, cookiecutter, binaryornot, chardet, cssselect2, tinycss2,
webencodings, jinja2, markupsafe, lxml, pyyaml, qrcode, requests,
text-unidecode, python-slugify, python-dateutil, tzdata, arrow, urllib3,
watchfiles. Also pruned unused `flet-cli`/`flet-desktop`/`flet-platform-assets`
that were not in the lock.

## Docs coverage vs packages
| Package | docs/reference entry |
|---|---|
| flet | **MISSING** (index references dep-flet.md) — compiled fresh |
| httpcore | folded into dep-httpx.md |
| colorama | covered in dep-pytest-stack.md (partial) |
| everything else | studied in docs/reference (re-verification agents) |
