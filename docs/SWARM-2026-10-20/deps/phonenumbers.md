# phonenumbers 9.0.41 — Dependency Audit (Sherlock V3)

**Auditor:** dependency-audit subagent (phonenumbers-exclusive lane)
**Date:** 2026-10-20
**Source of truth:** the installed venv — `/home/maikel/.zcode/workspace/default/Sherlock-V3/.venv/Lib/site-packages/phonenumbers`
**Package:** `phonenumbers` 9.0.41 (`phonenumbers-9.0.41.dist-info`), Python 3.14.7, Apache-2.0
**Companion report (read first, not duplicated here):** `docs/SWARM-2026-10-20/deps/phonsint.md` — that report owns the *phone-mode wiring* (how phonsint is called, the B1–B20 bug list). **This report owns phonenumbers' own API surface, its unused capabilities, and the removal-safety analysis.**
**Background doc (V2-era, re-verified here):** `docs/reference/dep-phonenumbers.md`
**No app files were modified.**

---

## 1) Installed API Verification (real command outputs)

### 1.1 Identity

```
$ grep -n "__version__" .venv/Lib/site-packages/phonenumbers/__init__.py
149:__version__ = "9.0.41"
```

`phonenumbers/__init__.py:145-149` states the version is *"taken from the upstream libphonenumber version together with an indication of the version of the Python-specific code"* — so the bundled **libphonenumber metadata is 9.0.41**, and all data tables (`data/`, `geodata/`, `carrierdata/`, `tzdata/`, `shortdata/`) are from that same release. Confirmed on disk: `data/region_US.py` is an auto-generated file whose metadata (`country_code=1`, `international_prefix='011'`, `national_number_pattern='[2-9]\\d{9}|3\\d{6}'`) matches libphonenumber 9.0.41.

Installed tree (real `ls`):

```
phonenumbers/
├── __init__.py          (9,802 B)   re-exports + __all__
├── asyoutypeformatter.py (33,119 B)
├── carrier.py           (6,353 B)
├── geocoder.py          (10,945 B)
├── phonemetadata.py     (34,110 B)
├── phonenumber.py       (13,197 B)
├── phonenumbermatcher.py(38,606 B)
├── phonenumberutil.py   (164,404 B)  ← all core logic
├── prefix.py / re_util.py / unicode_util.py / util.py
├── carrierdata/  6 files   1,005,087 B
├── data/         303 files    568,607 B
├── geodata/      34 files 19,552,261 B
├── shortdata/   244 files    214,309 B
├── tzdata/         4 files    116,222 B
└── py.typed / *.pyi (full type stubs shipped)
```

### 1.2 `parse()` — signature and the region requirement (source-verified)

`phonenumbers/phonenumberutil.py:2882-2883`
```python
def parse(number, region=None, keep_raw_input=False,
          numobj=None, _check_region=True):
```

The region requirement is enforced at `phonenumberutil.py:2957-2959`:
```python
if _check_region and not _check_region_for_parsing(national_number, region):
    raise NumberParseException(NumberParseException.INVALID_COUNTRY_CODE,
                               "Missing or invalid default region.")
```
and `_check_region_for_parsing` (`phonenumberutil.py:2851-2864`) returns `True` only if the region code is valid **or** the number starts with a `+`/IDD. So: **`region` is required for national-format numbers; it may be `None` for `+`-prefixed (international) numbers.** `region="ZZ"` is *not* a valid parse region (that sentinel only means "plus-only" in `PhoneNumberMatcher`).

Other failure exits in `parse()`: `NOT_A_NUMBER` at `:2951-2953` (fewer than 3 digits / non-number), `TOO_LONG` at `:2945-2947` (>250 chars), `TOO_SHORT_NSN` at `:3012-3014` (<2 digits NSN), plus `INVALID_COUNTRY_CODE` at `:2989-2991` ("Could not interpret numbers after plus-sign").

### 1.3 `NumberParseException` — the five error types

`phonenumbers/phonenumberutil.py:3337` (class) / `:3344-3370` (constants), verified live:

```
NumberParseException.INVALID_COUNTRY_CODE   = 0
NumberParseException.NOT_A_NUMBER           = 1
NumberParseException.TOO_SHORT_AFTER_IDD    = 2
NumberParseException.TOO_SHORT_NSN          = 3
NumberParseException.TOO_LONG               = 4
```
It subclasses `(UnicodeMixin, Exception)` and carries `.error_type` (int) and `._msg`. `__reduce__` (`:3373`) makes it picklable.

### 1.4 `PhoneNumberFormat` — the four formats

`phonenumbers/phonenumberutil.py:420-455` (class docstring at `:420`), live values:

```
E164 = 0 | INTERNATIONAL = 1 | NATIONAL = 2 | RFC3966 = 3
```

### 1.5 Formatting / validation / region APIs — location + live output

Definitions (installed source):
| API | file:line |
|---|---|
| `format_number(numobj, num_format)` | `phonenumberutil.py:1082` |
| `is_valid_number(numobj)` | `phonenumberutil.py:2103` |
| `is_valid_number_for_region(numobj, region_code)` | `phonenumberutil.py:2124` |
| `is_possible_number(numobj)` | `phonenumberutil.py:2335` |
| `is_possible_number_with_reason(numobj)` | `phonenumberutil.py:2452` |
| `region_code_for_number(numobj)` | `phonenumberutil.py:2160` |
| `region_code_for_country_code(cc)` | `phonenumberutil.py:2206` |
| `region_codes_for_country_code(cc)` | `phonenumberutil.py:2206` (sibling) |
| `country_code_for_region(region)` | `phonenumberutil.py:2238` |
| `SUPPORTED_REGIONS` | `phonenumberutil.py:613` (`SUPPORTED_REGIONS = set()`) |
| `number_type(numobj)` | `phonenumberutil.py` (`PhoneNumberType`) |
| `AsYouTypeFormatter` | `asyoutypeformatter.py:85` (class), `:257` (`input_digit`) |
| `geocoder.description_for_number(num, lang)` | `geocoder.py` |
| `carrier.name_for_number(num, lang)` | `carrier.py` |
| `timezone.time_zones_for_number(num)` | `timezone.py` |
| `shortnumberinfo.*` | `shortnumberinfo.py:66/86/110/137/325/347/431/459` |
| `PhoneNumberMatcher` / `PhoneNumberMatch` | `phonenumbermatcher.py:445` / `:728` |

**`format_number` — real output**

```
--- input '+14155552671' region=None
    E164          = '+14155552671'
    INTERNATIONAL = '+1 415-555-2671'
    NATIONAL      = '(415) 555-2671'
    RFC3966       = 'tel:+1-415-555-2671'
--- input '07700900123' region='GB'
    E164          = '+447700900123'
    INTERNATIONAL = '+44 7700 900123'
    NATIONAL      = '07700 900123'
    RFC3966       = 'tel:+44-7700-900123'
--- input '4155552671' region='US'
    E164          = '+14155552671'
    INTERNATIONAL = '+1 415-555-2671'
    NATIONAL      = '(415) 555-2671'
    RFC3966       = 'tel:+1-415-555-2671'
```

Extension handling (also live): `parse("+1 415 555 2671 ext. 123")` → `extension='123'`, RFC3966 → `'tel:+1-415-555-2671;ext=123'`, `format_number_for_mobile_dialing(p,"GB",True)` → `'+1 415-555-2671'`.

**`is_valid_number` vs `is_possible_number` — real output**

```
input                  region    valid    possible type     region_cd  cc_for_region
'+14155552671'         None      True     True     2        'US'       1
'+14155552670'         None      True     True     2        'US'       1
'4155552671'           'US'      True     True     2        'US'       1
'415555267'            'US'      False    False    99       None       n/a
'+999123456789'        None      RAISED 0
'07700900123'          'GB'      False    True     99       None       n/a
'+33629987654'         None      True     True     1        'FR'       33
'+447700900123'        None      False    True     99       None       n/a
```

The distinction is exactly as documented upstream: `is_possible_number` is a **length** check (`:2335`), `is_valid_number` is a **full pattern** check against the region's allocation regexes (`:2103` → `:2124`). `415555267` (9 digits) is *neither* possible nor valid; `07700900123` is *possible* but *not valid* (reserved UK drama range) — this is the pair of states a UI needs to distinguish "still typing" from "wrong number".

`is_possible_number_with_reason` (`:2452`) returns a `ValidationResult`:
```
'+14155552671' -> ValidationResult=0 (IS_POSSIBLE)   is_possible=True
'415555267'    -> ValidationResult=2 (TOO_SHORT)      is_possible=False
```
`ValidationResult` int map (live): `IS_POSSIBLE=0, INVALID_COUNTRY_CODE=1, TOO_SHORT=2, TOO_LONG=3, IS_POSSIBLE_LOCAL_ONLY=4, INVALID_LENGTH=5`.
`PhoneNumberType` int map (live): `FIXED_LINE=0, MOBILE=1, FIXED_LINE_OR_MOBILE=2, TOLL_FREE=3, PREMIUM_RATE=4, SHARED_COST=5, VOIP=6, PERSONAL_NUMBER=7, PAGER=8, UAN=9, VOICEMAIL=10, UNKNOWN=99`.

**`region_code_for_number` / `country_code_for_region` / `region_code_for_country_code` — real output**

```
  country_code_for_region('US') = 1
  country_code_for_region('GB') = 44
  country_code_for_region('CH') = 41
  country_code_for_region('NG') = 234
  country_code_for_region('DE') = 49
  country_code_for_region('FR') = 33
  country_code_for_region('JP') = 81
  country_code_for_region('ZZ') = 0
  region_code_for_country_code(1   ) = 'US' ; codes_for_cc=('US','AG','AI','AS','BB','BM','BS','CA','DM','DO','GD','GU','JM','KN','KY','LC','MP','MS','PR','SX','TC','TT','VC','VG','VI')   # 25 NANPA territories
  region_code_for_country_code(44  ) = 'GB' ; codes_for_cc=('GB','GG','IM','JE')
  region_code_for_country_code(41  ) = 'CH' ; codes_for_cc=('CH',)
  region_code_for_country_code(234 ) = 'NG' ; codes_for_cc=('NG',)
  supported_calling_codes count = 215
```
Note the shared-country-code behaviour: `region_code_for_number` returns `None` for a `+44 7700…` number (UK mobile has no distinguishable area code) — this is why `phonsint`'s `PhoneInfo.region_code` is `''` for GB mobiles.

### 1.6 `SUPPORTED_REGIONS` — real count

```
SUPPORTED_REGIONS len = 245
sample sorted         = ['AC','AD','AE','AF','AG','AI','AL','AM','AO','AR','AS','AT', ...]
'US' in = True | 'GB' = True | 'ZZ' = False
```
**245 region codes** (the V2 doc's "~250" is close; 245 is the exact number). `SUPPORTED_REGIONS` is a `set` (`phonenumberutil.py:613`), populated lazily as region metadata is loaded — it is fully populated at import time because the package registers all loaders up front.

### 1.7 `AsYouTypeFormatter` — real output (correct usage)

`input_digit()` returns the *whole accumulated formatted string* on every call; the **last** return value is the formatted text. (A naive `"".join(...)` over the returns produces garbage — the format templates change as more digits arrive, so earlier returns are superseded. Getting this wrong is an easy way to ship a broken live formatter.)

```
  region=US  input='4155552671'     -> '(415) 555-2671'
  region=US  input='415555'         -> '415-555'
  region=US  input='415'            -> '415'
  region=US  input='4'              -> '4'
  region=GB  input='07700900123'    -> '07700 900123'
  region=GB  input='07700900'       -> '07700 900'
  region=GB  input='077'            -> '077'
  region=NG  input='08031234567'    -> '0803 123 4567'
  region=DE  input='015123456789'   -> '01512 3456789'
  region=US  input='+14155552671'   -> '+1 415-555-2671'
```
**`"4155552671"` → `"(415) 555-2671"`** — confirms the phonsint report's §1.8 claim with a direct call, and confirms the formatter handles a `+`-prefixed international string too.

### 1.8 Optional heavy data modules — real import cost

Per-module wall time, each in a **fresh process** (baseline bare interpreter = 0.10 s):

```
  baseline (bare interpreter)                       0.10 s
  import phonenumbers                               0.17 s
  import phonenumbers.timezone                      0.16 s
  import phonenumbers.shortnumberinfo               0.16 s
  import phonenumbers.phonenumbermatcher            0.15 s
  import phonenumbers.carrier                       0.21 s
  import phonenumbers.geocoder                      0.64 s
```
In-process (core already imported, no tracemalloc):
```
  phonenumbers.geocoder        import=   322.0 ms
  phonenumbers.carrier         import=    25.2 ms
  phonenumbers.timezone        import=     3.5 ms
  phonenumbers.shortnumberinfo import=     0.0 ms
  phonenumbers.phonenumbermatcher import=   0.0 ms
```
**Verdict: `geocoder` is the only genuinely expensive one (~0.3–0.5 s, 19.5 MB of Python data modules to import).** `carrier` is ~25 ms, `timezone` ~3.5 ms, `shortnumberinfo` and `phonenumbermatcher` are free. Core `phonenumbers` costs ~70 ms net. (A `tracemalloc`-instrumented run inflates this to 396 s for geocoder and shows a ~92 MB traced peak — that number is a tracing artefact, not a real cost; use the wall-clock figures above. The V2 doc's "~110 KB RAM for core import" remains the right order of magnitude for the core.)

**Empirical output of the heavy modules**

```
  +14155552671     region=US   geo='San Francisco, CA'  carrier=''             tz=('America/Los_Angeles',)
  +447700900123    region=     geo=''                   carrier=''             tz=('Etc/Unknown',)
  +33629987654     region=FR   geo='France'             carrier='SFR'          tz=('Europe/Paris',)
  +4915123456789   region=DE   geo='Germany'            carrier='T-Mobile'     tz=('Europe/Berlin',)
  +2348031234567   region=NG   geo='Nigeria'            carrier='MTN'          tz=('Africa/Lagos',)
  +18002220123     region=US   geo=''                   carrier=''             tz=('America/Adak', 'America/Anchorage', ... 41 zones)
  geo fr = 'France'
```
Caveats visible in the data: **US `555-01xx` numbers have no carrier** (`carrier=''`), `+44 7700…` (UK mobile drama range) geocodes to `''` and has tz `('Etc/Unknown',)`, and the NANPA toll-free `+1800…` prefix returns **41 timezones**. A UI must therefore treat "empty geocoder/carrier string" and "multi-timezone list" as normal, not as errors.

**`shortnumberinfo` — real output** (note: the `*_for_region` variants take a **PhoneNumber object**, not a string — `shortnumberinfo.py:66/110/159/407/431` all dereference `numobj.country_code`; passing a str raises `AttributeError`):

```
  611            region=US  valid=True   possible=True   emergency=False  sms=False  cost=0
  911            region=US  valid=True   possible=True   emergency=True   sms=False  cost=0
  112            region=DE  valid=True   possible=True   emergency=True   sms=False  cost=0
  123            region=US  valid=False  possible=True   emergency=False  sms=False  cost=3
  404040         region=GB  valid=False  possible=True   emergency=False  sms=False  cost=3
  999            region=GB  valid=True   possible=True   emergency=True   sms=False  cost=0
  07700900123    region=GB  valid=False  possible=False  emergency=False  sms=False  cost=3
  SUPPORTED_SHORT_REGIONS len = 241
  is_valid_short_number(parse('611','US')) = True
  connects_to_emergency_number('911','US') = True
```
Correct call form: `sni.is_valid_short_number_for_region(phonenumbers.parse(num, region), region)`.

**`PhoneNumberMatcher` — bulk extraction, real output**

```
== default Leniency.VALID ==
  start=11  end=26  raw='+1 415-555-2671'  e164='+14155552671'
  start=53  end=66  raw='+442083661177'    e164='+442083661177'
== Leniency.POSSIBLE ==
  start=11  raw='+1 415-555-2671'  e164='+14155552671'
  start=30  raw='07700900123'      e164='+447700900123'
  start=53  raw='+442083661177'    e164='+442083661177'
```
Input text: `"Call me at +1 415-555-2671 or 07700900123 (UK). Fax: +442083661177. 555-CALL-NOW"`. `Leniency.VALID` (the default) **drops the bare national `07700900123`** because it is not a valid GB allocation; `Leniency.POSSIBLE` recovers it as `+447700900123`. Vanity strings (`555-CALL-NOW`) are never matched. `PhoneNumberMatch` exposes `.start`, `.end`, `.raw_string`, `.number` (**not** `.length` — that attribute does not exist in 9.0.41).

### 1.9 Other useful installed APIs (verified live)

```
  example_number('US')            = +12015550123
  format_in_original_format(NAT)  = '+1 415-555-2671'
  is_number_geographical          = True
  ndd_prefix_for_region('US', True) = '1'
  can_be_internationally_dialled  = True
  is_valid_number_for_region(+14155552671, 'GB') = False
  length_of_national_destination_code = 3
  length_of_geographical_area_code    = 3
  country_code_for_valid_region('US') = 1
```
`is_valid_number_for_region(+14155552671, "GB") == False` is the exact hook needed for a *"this number's country doesn't match the region you selected"* warning.

---

## 2) Empirical parse behavior for tricky inputs

### 2.1 Raw `phonenumbers.parse` (no phonsint wrapper)

```
parse('4155552671'      , None ) -> NumberParseException error_type=0 msg='(0) Missing or invalid default region.'
parse('4155552671'      , 'US' ) -> cc=1  nsn=4155552671   e164='+14155552671'
parse('+14155552671'    , None ) -> cc=1  nsn=4155552671   e164='+14155552671'
parse('+14155552671'    , 'GB' ) -> cc=1  nsn=4155552671   e164='+14155552671'
parse('07700900123'     , 'GB' ) -> cc=44 nsn=7700900123   e164='+447700900123'
parse('07700900123'     , None ) -> NumberParseException error_type=0 msg='(0) Missing or invalid default region.'
parse('(415) 555-2671'  , 'US' ) -> cc=1  nsn=4155552671   e164='+14155552671'
parse('(415) 555-2671'  , None ) -> NumberParseException error_type=0 msg='(0) Missing or invalid default region.'
parse('+1 415 555 2671' , None ) -> cc=1  nsn=4155552671   e164='+14155552671'
parse('020 8366 1177'   , 'GB' ) -> cc=44 nsn=2083661177   e164='+442083661177'
parse('abc'             , None ) -> NumberParseException error_type=1 msg='(1) The string supplied did not seem to be a phone number.'
parse(''                , None ) -> NumberParseException error_type=1 msg='(1) The string supplied did not seem to be a phone number.'
parse('+999123456789'   , None ) -> NumberParseException error_type=0 msg='(0) Could not interpret numbers after plus-sign.'
parse('4155552671'      , 'ZZ' ) -> NumberParseException error_type=0 msg='(0) Missing or invalid default region.'
```

Key facts:
* `region` is **only** needed for non-`+` input. `parse("+14155552671", "GB")` still returns the **US** number — the `+` wins over the region, it does not conflict.
* `region="ZZ"` is rejected by `parse` (it is only a "plus-only" sentinel for `PhoneNumberMatcher`).
* An unknown country code after `+` raises `INVALID_COUNTRY_CODE` (0) with a *different* message ("Could not interpret numbers after plus-sign") than the missing-region case — both are error_type 0, so **the app must distinguish them by message or by trying both paths**, not by type alone.

### 2.2 The same inputs through phonsint's wrapper (the path the app actually uses)

```
parse_phone_number('4155552671'  , None ) -> is_valid=False e164='+4155552671'   region='CH' intl='+41 55552671'    natl='55552671'
parse_phone_number('4155552671'  , 'US' ) -> is_valid=True  e164='+14155552671'  region='US' intl='+1 415-555-2671' natl='(415) 555-2671'
parse_phone_number('+14155552671', None ) -> is_valid=True  e164='+14155552671'  region='US' intl='+1 415-555-2671' natl='(415) 555-2671'
parse_phone_number('07700900123' , None ) -> is_valid=False e164='+107700900123' region=''    intl='+1 07700900123'  natl='07700900123'
parse_phone_number('07700900123' , 'GB' ) -> is_valid=False e164='+447700900123' region=''    intl='+44 7700 900123' natl='07700 900123'
```

Two failure modes confirmed live (they are the *reason* a region picker is the single highest-value use of this package):
1. **Bare 10-digit `4155552671` with no region → silently reinterpreted as Swiss** `+41 55552671` (country code 41, CH). The `+`-prepend probe in `phonsint/core/parser.py:24` makes the number look international; libphonenumber then resolves `+41`.
2. **`07700900123` with no region → the `"US"` fallback fabricates `+107700900123`** (country code 1). The number is scanned against a dial code it does not have.

Both produce a **well-formed but wrong E.164** with `is_valid=False` — and the app never checks `is_valid` (see §3). Passing the right `region` fixes both, which is exactly what `phonenumbers` gives the app for free.

---

## 3) App usage opportunities mapped to files

**Current state: the app has ZERO direct phonenumbers usage.** Verified:
```
$ grep -rn "phonenumbers" src/ tests/          → (no hits)
$ grep -rln "import phonenumbers|from phonenumbers" .venv/Lib/site-packages/ | grep -v "^phonenumbers/"
    → phonsint\core\parser.py                    (the ONLY non-phonenumbers importer in the entire venv)
```
`phonsint/core/parser.py` is the only path into the package. Everything below is *available today* with no new dependency.

### 3.1 Region picker — source of truth = `SUPPORTED_REGIONS` (245)

| # | Where | What | Exact anchors |
|---|---|---|---|
| 1 | `src/screens/home_screen.py` | A country/dial-code picker on the home search bar. The list comes from `phonenumbers.SUPPORTED_REGIONS` (245) joined with `country_code_for_region()` for the `+NN` prefix. | The search bar is `ft.SearchBar` at `home_screen.py:1150-1213`; `state.search_mode == MODE_PHONE` is the branch point (the bar_hint_text at `:1155-1159` already switches on mode). The mode chip lives at `home_screen.py:1110-1141`. |
| 2 | `src/core/state.py` | Persist the chosen region (`state.phone_region`, default `None`/auto) + a `STORAGE_PHONE_REGION` key alongside the existing `STORAGE_PHONE_CONCURRENCY`. | `state.py:59-64` (phone result block), `state.py:79` (`phone_concurrency`), `state.py:168/230-236` (reset). |
| 3 | `src/main.py` | Feed the region through instead of the hardcoded `None`. | `main.py:1773` `region=None,` → `region=state.phone_region` |
| 4 | `src/services/phone_service.py` | Stop discarding the region. | `phone_service.py:126` declares `region: str | None = None`; `phone_service.py:198` passes a **hardcoded `None`** into `_run_worker` — this is the actual bug. |
| 5 | `src/services/user_scanner_compat.py` | `parse_phone_number(phone, region)` already accepts it. | `user_scanner_compat.py:316` |

**Important nuance — phonenumbers gives codes, not names.** `SUPPORTED_REGIONS` is a set of ISO-3166-1 alpha-2 codes; phonenumbers ships **no country-name table**. The app's `src/core/geo_utils.py` is "powered by pycountry" (`geo_utils.py:1,13-18`) and already has a `CountryInfo` dataclass with `name`/`flag` (`geo_utils.py:101-111`) plus `get_country_by_tag()` (`:113`) — but **`pycountry` is NOT installed in this venv** (verified: no `pycountry` in `.venv/Lib/site-packages/`), so `geo_utils` is permanently on its fallback path (`geo_utils.py:11-19`, `_PYCOUNTRY_AVAILABLE = False`). A region picker therefore needs one of: (a) add `pycountry` (pure-Python, and `geo_utils` becomes live again), (b) ship a 245-entry `{code: (name, flag, dial_code)}` static map, or (c) show only `+NN` + a flag emoji from a small embedded table. **phonenumbers remains the source of truth for *which* regions are valid and for their dial codes; it cannot supply display names.**

### 3.2 Live validation while typing (the single biggest UX win)

| # | Where | What |
|---|---|---|
| 6 | `src/screens/home_screen.py` | The search bar already has `on_change=_on_input_change` (`home_screen.py:1212`, handler at `:706-711`) — this is the exact hook for a live chip. In phone mode: run `is_possible_number` (typing in progress) and `is_valid_number` (done) and render a ✓/✗/⏳ status. `is_possible_number_with_reason` (`:2452`) gives a typed reason (`TOO_SHORT`, `INVALID_LENGTH`, …) for a precise helper string. |
| 7 | `src/screens/home_screen.py` | As-you-type formatting: `AsYouTypeFormatter(region)` on the same `on_change`. Measured: `"4155552671"` → `"(415) 555-2671"`, `"07700900123"` (GB) → `"07700 900123"`, `"08031234567"` (NG) → `"0803 123 4567"`. |
| 8 | `src/screens/home_screen.py` | The current gate is a no-op for phones: `home_screen.py:638-640` → `elif mode == MODE_PHONE: # phone numbers: accept anything non-empty; engine validates` / `pass`. A `try: parse(...) except NumberParseException` with `error_type` mapped to a message turns this into a real validator. |

### 3.3 E.164 as canonical identity (dedup)

| # | Where | What |
|---|---|---|
| 9 | `src/core/state.py` | The cache/history key is the **raw** string: `state.py:175` and `:183` → `key = f"{mode}:{query.strip().lower()}"`. `+14155552671`, `14155552671` and `+1 415-555-2671` are three different keys. Key on `format_number(parsed, E164)` instead → one target, one cache entry. |
| 10 | `src/main.py` | `state.current_username = phone_clean` (`main.py:1746`), `state.phone_results_address = phone_clean` (`main.py:1754`) and `phone_progress = PhoneSearchProgress(phone=phone_clean, ...)` (`main.py:1755`) all carry the raw string. The canonical E.164 computed inside the engine is discarded. |
| 11 | `src/services/phone_service.py` | `PhoneResult` (`phone_service.py:25-35`) has **no `phone` field**, and `_map_result` (`phone_service.py:50`) receives `phone_info` but never reads it (the `phone_info` parameter is dead). Add `e164`/`national`/`international`/`region` fields so a result card can say what was actually scanned. |
| 12 | `src/services/phone_service.py` | `PhoneSearchProgress.phone` (`phone_service.py:40`) — display the E.164 in the progress header so the user sees the canonical target, not what they typed. |

### 3.4 Display formatting

| # | Where | What |
|---|---|---|
| 13 | `src/screens/results_screen.py` | The phone card branch (`results_screen.py:443-470`) renders `PhoneResult` into the shared email-card dict. It has room for a canonical line: `NATIONAL` `(415) 555-2671` as the display string, `E164` as the identity, `INTERNATIONAL` for the header. |
| 14 | `src/screens/results_screen.py` | `RFC3966` gives a `tel:` URI (`tel:+1-415-555-2671`) — the correct payload for a "call / copy as dialable" action, and it round-trips through `parse()` (RFC3966 input is accepted). |

### 3.5 "Best-effort number" warning (upstream CLI has it; the app does not)

| # | Where | What |
|---|---|---|
| 15 | `src/main.py` / `src/services/phone_service.py` | `phonsint/__main__.py:117-119` prints *"Warning: '…' is not a standard allocated number according to E.164"* and *"Proceeding with best-effort scan anyway"*. The app has **no equivalent** — it scans a mis-parsed `+107700900123` silently. The warning can be reproduced faithfully with `is_valid_number` + `number_type` (99 = UNKNOWN) + `is_valid_number_for_region(parsed, selected_region)`. |
| 16 | `src/services/phone_service.py` | `phone_service.py:176` drops the `"error"` tuple; a pre-flight parse error should instead be surfaced as a first-class progress/error event. |

### 3.6 Extra capabilities the app has no equivalent for

| # | Where | What |
|---|---|---|
| 17 | `src/screens/home_screen.py` | **Bulk number extraction.** `PhoneNumberMatcher` on a pasted text/file turns arbitrary prose into a list of candidate numbers. The app already has a bulk file picker (`home_screen.py:676+`). Measured: `Leniency.VALID` found `+1 415-555-2671` and `+442083661177`; `Leniency.POSSIBLE` additionally found the bare `07700900123` (as `+447700900123`). |
| 18 | `src/screens/home_screen.py` | **Short-code / emergency detection.** `shortnumberinfo.is_valid_short_number_for_region` / `is_emergency_number` (241 short regions installed) can warn "this is an SMS short code / emergency number, not a subscriber line — a scan will find nothing". Measured: `911`/`999` → emergency, `07700900123` → not a short number, cost 3. |
| 19 | `src/screens/results_screen.py` / a new target card | **Country / carrier / timezone context** — the "modern phone-OSINT" payload. Measured: `+2348031234567` → geo `'Nigeria'`, carrier `'MTN'`, tz `('Africa/Lagos',)`; `+4915123456789` → `'Germany'`/`'T-Mobile'`/`'Europe/Berlin'`; `+14155552671` → `'San Francisco, CA'`/`''`/`'America/Los_Angeles'`. **Import `geocoder` lazily** (it costs ~0.3–0.5 s and 19.5 MB of data modules); `carrier` (~25 ms) and `timezone` (~3.5 ms) are cheap enough to import inside the card builder too. Empty strings and multi-zone lists are normal (see §1.8) and must be handled as "unknown", not as errors. |
| 20 | `src/screens/results_screen.py` | **Number type as an OSINT hint** — `number_type` gives `MOBILE`/`VOIP`/`TOLL_FREE`/`PREMIUM_RATE`/… and `is_number_geographical` separates geographic from non-geographic. A VoIP or premium-rate hit is itself a finding. |

---

## 4) Removal-safety (who would orphan)

### 4.1 What imports phonenumbers today

```
$ grep -rln "import phonenumbers|from phonenumbers" .venv/Lib/site-packages/ | grep -v "phonenumbers/"
phonsint\core\parser.py
```
That is the **complete** list. Inside the package itself the importers are `phonenumbers/__init__.py`, `phonenumberutil.py`, `geocoder.py`, `carrier.py`, `timezone.py`, `phonenumbermatcher.py` — internal.

App side:
```
$ grep -rn "phonenumbers" src/ tests/     → (no hits)
```
**The app never imports phonenumbers directly.** It is a *transitive* dependency: `pyproject.toml:11` declares `phonsint>=0.1.0`, and `phonsint/core/parser.py` pulls phonenumbers in. **`phonenumbers` is not declared in `pyproject.toml` at all** (grep confirms: only `phonsint` at `:11`).

### 4.2 The installed `user_scanner` (1.5.2.3) is clean

```
$ grep -rn "phonenumbers" .venv/Lib/site-packages/user_scanner/
(no hits)
$ ls .venv/Lib/site-packages/user_scanner/
__init__.py  __main__.py  cli/  config.json  core/  email_scan/  mcp/  user_scan/  utils/  version.json
```
`user_scanner` (the username/email engine) has **zero** phonenumbers references. Its `core/` contains `confidence.py`, `cross_scan.py`, `email_orchestrator.py`, `engine.py`, `formatter.py`, `pivots.py`, `hudson.py`, `nextjs.py`, `pdf_generator.py`, etc. — none of them touch phone parsing. The phone capability in this venv comes **only** from `phonsint`.

### 4.3 Orphan matrix

| If… | Then… |
|---|---|
| **phonsint is removed** (owner's stated option) | phonenumbers is **fully orphaned** — nothing else in the venv imports it, the app never imports it, and `pyproject.toml` never declared it. Removing phonsint removes phonenumbers transitively, for free, with **no `pyproject.toml` edit** for phonenumbers itself (only `phonsint>=0.1.0` at `:11` needs dropping). This matches the phonsint report's §5 "Dependencies" conclusion. |
| **phonsint is kept** | phonenumbers stays as a *transitive* dependency only. The app keeps zero direct usage, so every capability in §3 remains unexercised and phonenumbers upgrades/fixes are invisible to the app except through the 8-field `PhoneInfo` dataclass. |
| **The app adopts phonenumbers directly** (this report's recommendations) | phonenumbers must be **promoted to a declared direct dependency** in `pyproject.toml:7-12` (add `phonenumbers>=9.0.41`) — otherwise it is an undeclared transitive dependency, which is fragile: any future change to `phonsint`'s dependencies would silently break the app's phone feature. |
| **Both phonsint and phonenumbers are removed** | No orphan remains; phone mode disappears entirely. The removal is mechanically clean because the phone path is isolated behind `src/services/phone_service.py` + `src/services/user_scanner_compat.py:294-378` (see the phonsint report §5 for the full file:line blast radius). No shared username/email engine code depends on either package. |

### 4.4 Cost/risk of each path

| Path | Cost | Risk |
|---|---|---|
| Keep as-is | 0 lines changed | The phone mode stays broken (B1 crash, B3 region dropped, B9 no dedup, B11 no validity warning) and phonenumbers' value is fully unrealised. |
| Keep + adopt phonenumbers directly | ~150-250 lines across 6 files (region picker, live validation chip, E.164 canonicalisation, context card) + 1 line in `pyproject.toml` | Low. Pure-Python, no native ext, core import ~70 ms, geocoder lazily imported. Directly fixes B3, B9, B11 from the phonsint report. |
| Remove phonsint | ~800 lines deleted across 1 service file, ~15 call sites, 6 test files | Low, and mechanically clean. The app loses a 5-platform phone mode. phonenumbers disappears with it. |

---

## 5) Verdict

# UNUSED-OPPORTUNITY

**The package itself is PERFECT; the app's adoption of it is a missed opportunity.**

*Why the package is PERFECT:* installed and working exactly as documented, no version drift (9.0.41 metadata, 9.0.41 libphonenumber tables), no import errors, full `.pyi` type stubs + `py.typed` marker, all five `NumberParseException` types correct, `parse()`'s region contract exactly as documented, 245 supported regions, 241 short-code regions, and every documented API (`format_number` × 4 formats, `is_valid_number` vs `is_possible_number`, `region_code_for_number`, `country_code_for_region`, `AsYouTypeFormatter`, `geocoder`, `carrier`, `timezone`, `shortnumberinfo`, `PhoneNumberMatcher`) empirically verified working in this venv. Import cost is well-behaved: core ~70 ms net, and only `geocoder` (0.3-0.5 s, 19.5 MB) needs lazy loading.

*Why it is an UNUSED-OPPORTUNITY:* **the app uses 0 of it directly** (`grep -rn "phonenumbers" src/ tests/` → no hits), and it is not even a declared dependency — it is pulled in transitively by `phonsint/core/parser.py`, the single non-phonenumbers importer in the whole venv. Concretely, the app is missing:

* a **region picker** (the one thing that makes national-format numbers parse at all — and without it, `4155552671` is silently scanned as a **Swiss** number `+4155552671`, and `07700900123` is scanned as a **fabricated US** number `+107700900123`);
* **live validation** while typing (the input gate at `home_screen.py:638-640` is an explicit `pass`);
* **E.164 canonical identity** (`+14155552671` / `14155552671` / `+1 415-555-2671` are three cache/history entries today);
* **the "best-effort number" warning** the upstream CLI prints (`phonsint/__main__.py:117-119`) and the app does not;
* **the whole OSINT context layer** — geocoder (`'Nigeria'`), carrier (`'MTN'`), timezone (`'Africa/Lagos,'`), number type, short-code detection, and bulk number extraction.

*Recommendation:* if phone mode stays, promote `phonenumbers` to a **declared direct dependency** (`pyproject.toml:7-12`) and implement §3.1-§3.5 — the region picker alone eliminates the two silent-misparse defects that make the current phone mode actively wrong, and the E.164 keying removes the duplicate-target problem in the cache and history. If phone mode goes, phonenumbers leaves with it at zero cost and zero orphan risk (it is not declared in `pyproject.toml`, and the installed `user_scanner` has no reference to it whatsoever). Either way, **the current state — a working library entirely unused behind a transitive import — is the worst of both options.**

---

*No app files were modified during this audit. Only this report was created.*
