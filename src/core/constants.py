"""Application-wide constants."""

APP_NAME = "Sherlock"
APP_VERSION = "2.2.0"
APP_BUILD_NUMBER = 12

# ── Update & Distribution URLs ─────────────────────────────────────────
UPDATE_CONFIG_URL = (
    "https://raw.githubusercontent.com/Nwokike/Sherlock/main/version.json"
)
PLAY_STORE_URL = "https://play.google.com/store/apps/details?id=ng.kiri.sherlock"
GITHUB_RELEASES_URL = "https://github.com/Nwokike/Sherlock/releases/latest"

# ── Storage keys ──────────────────────────────────────────────────────
STORAGE_HISTORY = "sherlock_history"
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
STORAGE_ENRICHMENT_MODE = "sherlock_enrichment_mode"
STORAGE_NO_PASSWORD_RECOVERY = "sherlock_no_pw_recovery"
STORAGE_SEARCH_KEYWORDS = "sherlock_search_keywords"
STORAGE_DEEP_ENRICH = "sherlock_deep_enrich"
STORAGE_COOKIES_PATH = "sherlock_cookies_path"
STORAGE_TOR_PROXY = "sherlock_tor_proxy"
STORAGE_I2P_PROXY = "sherlock_i2p_proxy"
STORAGE_CHECK_DOMAINS = "sherlock_check_domains"
STORAGE_DB_UNHEALTHY = "sherlock_db_unhealthy"
STORAGE_BIOMETRIC_LOCK = "sherlock_biometric_lock"
STORAGE_SCAN_DEPTH = "sherlock_scan_depth"
STORAGE_CACHED_RESULTS = "sherlock_cached_results"
STORAGE_RECURSIVE_SEARCH = "sherlock_recursive_search"
STORAGE_EXTRACT_INFO = "sherlock_extract_info"
STORAGE_MAX_CONNECTIONS = "sherlock_max_connections"
STORAGE_RETRIES = "sherlock_retries"
STORAGE_DNS_RESOLVER = "sherlock_dns_resolver"
STORAGE_USE_CURL_CFFI = "sherlock_use_curl_cffi"
STORAGE_SAFE_SEARCH = "sherlock_safe_search"

# ── Search modes ──────────────────────────────────────────────────────
MODE_USERNAME = "username"
MODE_EMAIL = "email"

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

# ── Email OSINT constants ─────────────────────────────────────────────
# Validator names skipped by the "No Password Recovery" setting.
# holehe-v2 dropped the per-module method metadata this list was derived
# from; adobe is the only platform from the original set that still
# ships a validator (mail_ru / odnoklassniki / samsung are absent from
# v2's 181 modules — kept as no-ops in case they return).
EMAIL_PW_RECOVERY_MODULES = frozenset({"adobe", "mail_ru", "odnoklassniki", "samsung"})
