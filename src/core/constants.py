"""Application-wide constants.

Storage-key lifecycle notes: every STORAGE_* key below is both written and
restored (main.py:_load_saved_state) unless commented otherwise.
"""

import os

# UI-automation hook: with SHERLOCK_TEST_IDS=1 the major interactive
# controls carry key= identifiers so test drivers can target them
# deterministically. Off by default — zero cost in production.
USE_TEST_IDS = os.environ.get("SHERLOCK_TEST_IDS", "") == "1"


def test_id(name: str) -> str | None:
    """Return the automation id when test mode is on, else None."""
    return name if USE_TEST_IDS else None


APP_NAME = "Sherlock"
APP_VERSION = "2.3.0"
APP_BUILD_NUMBER = 13

# Fallback module count shown before the module catalog load lands.
# user-scanner: 2,521 username + 220 email modules; phonsint: 5 phone modules.
# Verified against the installed catalog 2026-10-20.
SITES_TOTAL_FALLBACK = 2746

# ── Update & Distribution URLs ─────────────────────────────────────────
UPDATE_CONFIG_URL = (
    "https://raw.githubusercontent.com/Nwokike/Sherlock/main/version.json"
)
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.sherlock"
GITHUB_RELEASES_URL = "https://github.com/Nwokike/Sherlock/releases/latest"

# ── Storage keys ──────────────────────────────────────────────────────
STORAGE_HISTORY = "sherlock_history"  # read on demand (history screens)
STORAGE_THEME = "sherlock_theme"
STORAGE_CACHED_SITES = "sherlock_cached_sites"
STORAGE_NSFW = "sherlock_nsfw"
STORAGE_EXCLUSIONS = "sherlock_exclusions"
STORAGE_TIMEOUT = "sherlock_timeout"
STORAGE_LOCAL_DB = "sherlock_local_db"
STORAGE_SELECTED_SITES = "sherlock_selected_sites"
STORAGE_ONBOARDING_DONE = "sherlock_onboarding_done"
STORAGE_MANIFEST = "sherlock_manifest"
STORAGE_SEARCH_MODE = "sherlock_search_mode"
STORAGE_EMAIL_TIMEOUT = "sherlock_email_timeout"
STORAGE_EMAIL_CONCURRENCY = "sherlock_email_concurrency"
STORAGE_EMAIL_ONLY_FOUND = "sherlock_email_only_found"
STORAGE_PROXY_URL = "sherlock_proxy_url"
STORAGE_NO_PASSWORD_RECOVERY = "sherlock_no_pw_recovery"  # noqa: S105 — variable name contains "password"; the value is a storage key
STORAGE_SEARCH_KEYWORDS = "sherlock_search_keywords"
STORAGE_DEEP_ENRICH = "sherlock_deep_enrich"
STORAGE_COOKIES_PATH = "sherlock_cookies_path"
STORAGE_I2P_PROXY = "sherlock_i2p_proxy"
STORAGE_CHECK_DOMAINS = "sherlock_check_domains"
STORAGE_DB_UNHEALTHY = "sherlock_db_unhealthy"
STORAGE_SCAN_DEPTH = "sherlock_scan_depth"
STORAGE_CACHED_RESULTS = "sherlock_cached_results"
STORAGE_RECURSIVE_SEARCH = "sherlock_recursive_search"
STORAGE_PERMUTE = "sherlock_permute"
STORAGE_LOG_ENGINE_LOGS = "sherlock_log_engine_logs"
STORAGE_EXTRACT_INFO = "sherlock_extract_info"
STORAGE_MAX_CONNECTIONS = "sherlock_max_connections"
STORAGE_RETRIES = "sherlock_retries"
STORAGE_DNS_RESOLVER = "sherlock_dns_resolver"
STORAGE_USE_CURL_CFFI = "sherlock_use_curl_cffi"
STORAGE_ALLOW_LOUD = "sherlock_allow_loud"
STORAGE_SHOW_ALL_RESULTS = "sherlock_show_all_results"
STORAGE_VERBOSE_OUTPUT = "sherlock_verbose_output"
STORAGE_CROSS_SCAN = "sherlock_cross_scan"
STORAGE_CROSS_LINKS = "sherlock_cross_links"
STORAGE_CROSS_EMAILS = "sherlock_cross_emails"
STORAGE_CROSS_DEPTH = "sherlock_cross_depth"
STORAGE_CROSS_SWEEP = "sherlock_cross_sweep"
STORAGE_EMAIL_DOMAINS = "sherlock_email_domains"
STORAGE_HUDSON = "sherlock_hudson"
STORAGE_PROXY_FILE = "sherlock_proxy_file"
STORAGE_PHONE_CONCURRENCY = "sherlock_phone_concurrency"
STORAGE_SAFE_SEARCH = "sherlock_safe_search"

# ── Search modes ──────────────────────────────────────────────────────
MODE_USERNAME = "username"
MODE_EMAIL = "email"
MODE_PHONE = "phone"
# Single vocabulary for persist + restore so a new mode round-trips
# (main.py:695 filters with this tuple).
SEARCH_MODES = (MODE_USERNAME, MODE_EMAIL, MODE_PHONE)

# ── AdMob unit IDs ─────────────────────────────────────────────────────
AD_BANNER_UNIT_ID = "ca-app-pub-5679949845754640/5131365762"

# ── Error messages ────────────────────────────────────────────────────
ERR_NETWORK = "Network error. Check your connection."
ERR_GENERIC = "Something went wrong. Please try again."
ERR_OPEN_URL = "Couldn't open link — try again."
ERR_INVALID_EMAIL = "Please enter a valid email address."

# ── Connectivity messages ─────────────────────────────────────────────
MSG_OFFLINE = (
    "You're offline. Searching needs a connection — history and settings still work."
)
MSG_ONLINE = "You're back online."
MSG_SEARCH_OFFLINE = (
    "You're offline, so scans can't reach sites. Check your connection and try again."
)
