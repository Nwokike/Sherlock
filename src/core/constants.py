"""Application-wide constants."""

APP_NAME = "Sherlock"
APP_VERSION = "2.1.0"
APP_BUILD_NUMBER = 10

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
STORAGE_EMAIL_METHOD_FILTER = "sherlock_email_method_filter"
STORAGE_PROXY_URL = "sherlock_proxy_url"
STORAGE_ENRICHMENT_MODE = "sherlock_enrichment_mode"
STORAGE_NO_PASSWORD_RECOVERY = "sherlock_no_pw_recovery"
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
# holehe detection methods
EMAIL_METHOD_REGISTER = "register"
EMAIL_METHOD_LOGIN = "login"
EMAIL_METHOD_RECOVERY = "password recovery"
EMAIL_METHOD_OTHER = "other"

# Password-recovery modules that can be skipped via the
# "No Password Recovery" setting (holehe's -NP flag).
EMAIL_PW_RECOVERY_MODULES = frozenset({"adobe", "mail_ru", "odnoklassniki", "samsung"})
