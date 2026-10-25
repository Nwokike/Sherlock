# phonenumbers 9.0.41 — International Phone Number Parsing, Validation & Formatting

> Study verified against `.venv/Lib/site-packages/phonenumbers` and `.venv/Lib/site-packages/phonsint` in Sherlock-V2.
> Package: `phonenumbers 9.0.41` (`Apache-2.0`, Python port of Google's `libphonenumber`).
> Upstream / Origin: David Drysdale (`python-phonenumbers`), porting Google's C++/Java metadata and algorithms.
> Transitive chain: `sherlock-v2` (`pyproject.toml:10`) -> `phonsint>=0.1.0` (`pyproject.toml:10`, `uv.lock:348`) -> `phonenumbers` (`uv.lock:340`).

---

## 1. Identity, Version & Package Metadata

| Property | Value / Location |
| :--- | :--- |
| **Package Name** | `phonenumbers` |
| **Installed Version** | `9.0.41` |
| **Version Declaration** | `phonenumbers/__init__.py:149` (`__version__ = "9.0.41"`) |
| **Distribution Metadata** | `phonenumbers-9.0.41.dist-info/METADATA:3` (`Version: 9.0.41`) |
| **License** | Apache-2.0 (`phonenumbers-9.0.41.dist-info/METADATA:5`) |
| **Author / Maintainer** | David Drysdale `<dmd@lurklurk.org>` |
| **Project URL** | `https://github.com/daviddrysdale/python-phonenumbers` |
| **Upstream Base** | Google `libphonenumber` release 9.0.41 |

Package re-exports public symbols via `phonenumbers/__init__.py:98-124` and `phonenumbers/__init__.py:151-205` (`__all__`), exposing core functions and classes directly at top-level namespace: `phonenumbers.parse`, `phonenumbers.format_number`, `phonenumbers.is_valid_number`, `phonenumbers.region_code_for_number`, `phonenumbers.PhoneNumberFormat`, and `phonenumbers.NumberParseException`.

---

## 2. Core API Specifications & File:Line Citations

All primary logic resides in `phonenumbers/phonenumberutil.py` (3,401 lines) and `phonenumbers/phonemetadata.py` (320 lines).

### 2.1 `parse()` — Lenient Phone String Parser

- **Source Location**: `phonenumbers/phonenumberutil.py:2882-3041`
- **Signature**:
  ```python
  def parse(number, region=None, keep_raw_input=False,
            numobj=None, _check_region=True):
  ```
- **Behavior & Execution Flow**:
  1. **Input checks** (`:2942-2947`): Checks for `None` or length exceeding `_MAX_INPUT_STRING_LENGTH` (250 chars).
  2. **Sanitization** (`:2949-2954`): Strips formatting, extracts phone-viable characters, converts vanity alpha characters (e.g., `1-800-FLOWERS` -> `1-800-3569377`) via `_build_national_number_for_parsing()`.
  3. **Region validation** (`:2957-2959`): If `number` does not start with an international dialing prefix (`+` or IDD), `region` must be supplied and recognized as a valid region or `NumberParseException(INVALID_COUNTRY_CODE)` is raised.
  4. **Extension extraction** (`:2965-2967`): Strips carriers/extensions like `ext. 123` or `#123` into `numobj.extension`.
  5. **Country code resolution** (`:2973-3000`): Extracts numerical country code via leading digits or regional metadata mapping.
  6. **National prefix & carrier stripping** (`:3015-3029`): Normalizes domestic prefixes (e.g. leading `0` in UK/FR) and optional domestic carrier selection codes.
  7. **Length validation** (`:3012-3038`): Enforces `_MIN_LENGTH_FOR_NSN` (2 digits) and `_MAX_LENGTH_FOR_NSN` (17 digits).
  8. **Italian leading zeros** (`:3039`): Sets boolean flag for Italian leading zeros (e.g. `+39 02 ...`).
  9. **Return**: Populated mutable `PhoneNumber` instance (`country_code: int`, `national_number: int`, `extension: str`, `raw_input: str`).

### 2.2 `PhoneNumberFormat` — Output Format Enumeration

- **Source Location**: `phonenumbers/phonenumberutil.py:420-455`
- **Class Definition**:
  ```python
  class PhoneNumberFormat(object):
      E164 = 0
      INTERNATIONAL = 1
      NATIONAL = 2
      RFC3966 = 3
  ```
- **Format Representations**:
  - `E164 = 0`: Standard ITU-T E.164 string with leading `+` and no spaces, hyphens, or formatting punctuation (e.g., `+16502530000`, `+442083661177`). Essential for canonical indexing, OSINT target matching, and API queries.
  - `INTERNATIONAL = 1`: Human-readable international dialing representation according to ITU-T E.123 with whitespace and region-specific grouping (e.g., `+1 650-253-0000`, `+44 20 8366 1177`).
  - `NATIONAL = 2`: Domestic dialing presentation according to national carrier conventions with national trunk prefixes and area codes (e.g., `(650) 253-0000`, `020 8366 1177`).
  - `RFC3966 = 3`: URI telephone scheme format prefix `tel:` with hyphen delimiters and explicit extensions (e.g., `tel:+1-650-253-0000;ext=101`).

### 2.3 `format_number()` — Canonical & Display Formatting

- **Source Location**: `phonenumbers/phonenumberutil.py:1082-1138`
- **Signature**:
  ```python
  def format_number(numobj, num_format):
  ```
- **Behavior & Execution Flow**:
  1. **Zero national number check** (`:1101-1112`): If `numobj.national_number == 0`, attempts fallback to raw input if recorded.
  2. **E.164 fast exit** (`:1115-1119`): If `num_format == PhoneNumberFormat.E164`, prepends `+` and country calling code to the `national_significant_number(numobj)` directly without applying national grouping regexes.
  3. **Region metadata lookup** (`:1126-1130`): Calls `region_code_for_country_code(country_calling_code)` to find the formatting authority (for example, shared NANPA country code `1` resolves formatting through `US` metadata).
  4. **Pattern formatting** (`:1131-1138`): Matches number against `available_formats` regular expressions in the regional metadata, strips or keeps national prefix, appends formatted extension if present, and adds international prefix.

### 2.4 `is_valid_number()` & `is_valid_number_for_region()` — Structural Validation

- **Source Location**: `phonenumbers/phonenumberutil.py:2103-2121` (`is_valid_number`) and `:2124-2157` (`is_valid_number_for_region`)
- **Signature**:
  ```python
  def is_valid_number(numobj):
      region_code = region_code_for_number(numobj)
      return is_valid_number_for_region(numobj, region_code)
  ```
- **Validation Semantics**:
  - Validates full structural conformity against ITU-T and national regulatory allocations.
  - Matches length and digit pattern against all valid number types: fixed-line, mobile, toll-free, premium rate, shared cost, VOIP, personal number, pager, UAN, and voicemail (`phonenumbers/phonenumberutil.py:2157`, `_number_type_helper`).
  - **Crucial Distinction**: `is_valid_number()` does **NOT** verify whether a number is currently active, assigned to a subscriber, or online with a carrier. It only verifies that the number strictly conforms to valid dialing plan allocations for that territory.
  - **Contrast with `is_possible_number()`** (`:2044-2051`): `is_possible_number` only checks length boundaries for that country code, whereas `is_valid_number` tests specific area code and prefix regex ranges.

### 2.5 `region_code_for_number()` — Geocoding / Region Mapping

- **Source Location**: `phonenumbers/phonenumberutil.py:2160-2182`
- **Helper Function**: `phonenumbers/phonenumberutil.py:2185-2203` (`_region_code_for_number_from_list`)
- **Behavior**:
  1. Reads `numobj.country_code` and queries `COUNTRY_CODE_TO_REGION_CODE` (`:2175`).
  2. If the country code maps to exactly one ISO 3166-1 alpha-2 territory (e.g. `33` -> `FR`, `49` -> `DE`, `81` -> `JP`), immediately returns that region code (`:2179-2180`).
  3. If shared across multiple territories (e.g., country code `1` spans `US`, `CA`, `PR`, `GU`, `VI`, etc.; country code `44` spans `GB`, `GG`, `IM`, `JE`), executes `_region_code_for_number_from_list`:
     - Evaluates `metadata.leading_digits` regular expressions for each candidate region against `national_significant_number(numobj)` (`:2196-2200`).
     - Returns the matching 2-letter uppercase region code (e.g. `"US"` or `"CA"`), or `None` if unmapped.

### 2.6 `NumberParseException` — Parsing Error Handling

- **Source Location**: `phonenumbers/phonenumberutil.py:3337-3380`
- **Inheritance**: Subclasses `(UnicodeMixin, Exception)`
- **Attributes**: `error_type: int`, `_msg: str`
- **Enumerated Error Types**:
  ```python
  INVALID_COUNTRY_CODE = 0  # Country calling code invalid or missing without a default_region
  NOT_A_NUMBER = 1          # Input has < 3 digits or invalid characters/syntax
  TOO_SHORT_AFTER_IDD = 2   # International prefix detected, but remaining digits too few
  TOO_SHORT_NSN = 3         # Country code stripped, but national significant number is too short
  TOO_LONG = 4              # Number exceeds maximum possible digits (NSN > 17 digits)
  ```

---

## 3. Metadata Architecture & Memory Footprint

`phonenumbers` bundles complete international dialing plans and regional lookup datasets.

### 3.1 Disk Footprint Breakdown (`.venv/Lib/site-packages/phonenumbers/`)

Measured live on disk across 22.1 MB total package assets:

| Directory | Size on Disk | Files / Content Description |
| :--- | :--- | :--- |
| `geodata/` | **18.63 MB** (19,539,973 B) | Multi-lingual location mappings (`data0.py` ... `data1200.py`), covering city/province geocoding across ~40 languages. |
| `carrierdata/` | **0.95 MB** (1,000,991 B) | Mobile carrier name databases per country/prefix. |
| `data/` | **0.56 MB** (585,894 B) | Core telephony validation rules: ~250 region metadata files (`region_US.py`, `region_GB.py`, etc.). |
| Root package | **0.39 MB** (411,959 B) | `phonenumberutil.py`, `phonemetadata.py`, `as_you_type_formatter.py`, `matcher.py`. |
| `__pycache__/` | **0.26 MB** (268,988 B) | Compiled bytecode for imported core modules. |
| `shortdata/` | **0.21 MB** (220,079 B) | Short code, emergency, and SMS service numbers per country. |
| `tzdata/` | **0.11 MB** (116,222 B) | Time zone mappings by telephone prefix. |
| **Total** | **21.12 MB** | Complete package footprint |

### 3.2 Dynamic Lazy-Loading Mechanism

Despite the ~21 MB on disk, `phonenumbers` is engineered with fine-grained lazy loading to prevent high memory consumption:

1. **Loader Registration**:
   `phonenumbers/phonemetadata.py:261` initializes `PhoneMetadata._region_available` as a dictionary mapping ISO 3166-1 alpha-2 region codes to deferred import loader functions.
2. **On-Demand Import (`phonemetadata.py:275-284`)**:
   ```python
   @classmethod
   def metadata_for_region(kls, region_code, default=None):
       loader = kls._region_available.get(region_code, None)
       if loader is not None:
           kls._metadata_lock.acquire()
           loader(region_code)
           kls._region_available[region_code] = None
           kls._metadata_lock.release()
       return kls._region_metadata.get(region_code, default)
   ```
3. **Runtime Memory Profile**:
   - Initial `import phonenumbers`: loads 58 internal modules into `sys.modules`, consuming only **~110 KB** traced RAM (`tracemalloc`).
   - Parsing a US number (`parse("+1 650 253 0000")`): Dynamically imports exactly one metadata module (`phonenumbers.data.region_US`, ~50 KB file).
   - `geodata` (18.6 MB) and `carrierdata` (0.95 MB) live in separate sub-packages (`phonenumbers.geocoder` and `phonenumbers.carrier`). Unless those modules are explicitly imported, their large tables are **never loaded into memory**.

---

## 4. How `phonsint` Consumes `phonenumbers`

Sherlock-V2 incorporates `phonsint` (`pyproject.toml:10`) for multi-platform telephone number OSINT. `phonsint` relies on `phonenumbers` as its foundational parser and normalizer.

### 4.1 Parser Module: `phonsint/core/parser.py`

The entire parsing pipeline is defined in `phonsint/core/parser.py:1-61`:

```python
# phonsint/core/parser.py:6-16
@dataclass(frozen=True)
class PhoneInfo:
    """Represents a validated and normalized phone number for platform checks."""
    raw_input: str
    is_valid: bool
    e164: str
    international_format: str
    national_format: str
    country_code: int
    national_number: int
    region_code: str
```

`parse_phone_number(raw: str, default_region: Optional[str] = None) -> PhoneInfo` (`:19-60`) operates as follows:

1. **Sanitization & Prefix Handling** (`:23-25`):
   ```python
   cleaned = raw.strip()
   test_parse = cleaned if (cleaned.startswith("+") or default_region) else ("+" + cleaned)
   ```
   If user enters a number without `+` and no `default_region` is set, `phonsint` heuristically prepends `+` to test for international format.
2. **Two-Tier Resilient Parsing** (`:26-41`):
   ```python
   try:
       parsed = phonenumbers.parse(cleaned if cleaned.startswith("+") else test_parse, default_region)
   except phonenumbers.NumberParseException:
       try:
           parsed = phonenumbers.parse(cleaned, default_region or "US")
       except phonenumbers.NumberParseException:
           return PhoneInfo(
               raw_input=raw,
               is_valid=False,
               e164=cleaned,
               international_format=cleaned,
               national_format=cleaned,
               country_code=0,
               national_number=0,
               region_code="",
           )
   ```
   If parsing fails, it retries assuming `"US"` as the fallback region. If both fail, it returns an unvalidated `PhoneInfo(is_valid=False)`.
3. **Format Extraction & Normalization** (`:43-60`):
   - `:43`: `is_valid = phonenumbers.is_valid_number(parsed)`
   - `:44`: `e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)`
   - `:45`: `intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)`
   - `:46`: `natl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)`
   - `:47-48`: `country_code = parsed.country_code`, `national_number = parsed.national_number`
   - `:49`: `region_code = phonenumbers.region_code_for_number(parsed) or ""`

### 4.2 CLI & Orchestration Workflow

- **CLI Validation & Feedback** (`phonsint/__main__.py:114-119`):
  ```python
  phone_info = parse_phone_number(args.phone, args.region)
  print(f"\n Checking phone: {phone_info.e164}")
  if not phone_info.is_valid:
      print(f"[!] Warning: '{args.phone}' is not a standard allocated number according to E.164.")
      print(f"[*] Proceeding with best-effort scan anyway...\n")
  ```
- **Orchestrator Dispatch** (`phonsint/core/orchestrator.py:23, 39, 51-53, 124`):
  Passes either `phone_info` or `phone_info.e164` depending on module function signature reflection (`inspect.signature(func)`).
- **Platform Modules Consumption**:
  - `modules/shopping/amazon.py:27`: Uses `info.e164` (e.g. `+14155552671`).
  - `modules/auth/microsoft.py:58`: Uses `info.e164`.
  - `modules/social/facebook.py:26`: Uses `info.e164`.
  - `modules/social/instagram.py:32`: Uses `info.e164`.
  - `modules/crm/zoho.py:16-19`: Uses split fields:
    ```python
    if not info.is_valid or not info.country_code or not info.national_number:
        return Result.error(...)
    phone_target = f"{info.country_code}-{info.national_number}"
    ```

---

## 5. Architectural Relevance to Sherlock-V2 Phone-Mode UI

Sherlock-V2 adds phone intelligence alongside username scanning using Flet (`flet>=1.0.4`, `flet-ads>=1.0.4`). The capabilities and characteristics of `phonenumbers` dictate specific UI patterns:

### 5.1 Region Picker (Country Code Selector)
- **Problem**: When a user inputs a local number like `07911 123456` or `(415) 555-2671` without an international `+` prefix, `phonenumbers.parse` requires a default ISO 3166-1 alpha-2 region string (`"GB"`, `"US"`), or it raises `NumberParseException.INVALID_COUNTRY_CODE`.
- **UI Solution**: Provide a searchable country dropdown or flag picker in the Flet UI:
  - Populate country list from `phonenumbers.SUPPORTED_REGIONS` (~250 ISO territory codes).
  - Use `phonenumbers.country_code_for_region(region)` to display the calling prefix (e.g., `US (+1)`, `GB (+44)`, `NG (+234)`).
  - Store selected region code in UI state and pass directly as `default_region` into `parse_phone_number(raw_input, default_region)`.

### 5.2 Real-Time Live Validation & Formatting
- **Interactive Feedback**:
  - In Flet's `TextField.on_change` handler, evaluate user input against `phonenumbers.is_possible_number()` for quick length validity, and `phonenumbers.is_valid_number()` for complete pattern verification.
  - Display live status chips:
    - **Valid (Green Check)**: Show detected region flag, country name, and formatted preview.
    - **Malformed / Incomplete (Yellow / Red)**: Show inline helper text (`"Incomplete or unrecognized number format"`).
- **As-You-Type Formatting**:
  - `phonenumbers.AsYouTypeFormatter(region_code)` (`phonenumbers/asyoutypeformatter.py:98`) can format raw keystrokes on the fly (e.g., `415` -> `(415) `, `4155552671` -> `(415) 555-2671`).
- **Non-blocking Best-Effort Scan**:
  - Mirroring `phonsint`'s CLI behavior, do not rigidly disable the "Scan" button if a number fails `is_valid_number()`. Display a subtle confirmation or warning dialog (e.g., `"Number pattern is non-standard. Run best-effort OSINT scan anyway?"`), allowing investigation of VoIP or vanity numbers.

### 5.3 Canonical E.164 Display & Data Integrity
- **Standard Storage & OSINT Deduplication**:
  - Always normalize inputs to E.164 (`+<country><national>`) for internal state, scan caches, and database/evidence graphs.
  - Prevents split node identities in Sherlock-V2's NetworkX evidence graph (avoiding duplicate nodes for `(415) 555-2671` vs `+14155552671`).
- **UI Hierarchy**:
  - **Primary Headline**: Canonical E.164 (`+1 415 555 2671` or `+14155552671`) in scan headers and export cards.
  - **Secondary Subtitle**: Domestic `national_format` and region name (`US • California`) for human clarity.

### 5.4 Mobile & Desktop Performance Guardrails
- **Zero-lag Startup**:
  - Core `phonenumbers` import takes < 15 ms and allocates only ~110 KB RAM.
  - Avoid importing `phonenumbers.geocoder` or `phonenumbers.carrier` at app startup, as these load heavier localized text tables.
  - In mobile APK builds (via `flet build apk`), `phonenumbers` requires no native C-extensions or Flutter platform channels, making it 100% portable pure Python.
