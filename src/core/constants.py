"""Application-wide constants."""

APP_NAME = "Sherlock"
APP_VERSION = "1.4.0"

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


ERR_NETWORK = "Network error. Check your connection."
ERR_GENERIC = "Something went wrong. Please try again."
ERR_OPEN_URL = "Couldn't open link — try again."

# Connectivity messages
MSG_OFFLINE = (
    "You're offline. Searching needs a connection — history and settings still work."
)
MSG_ONLINE = "You're back online."
MSG_SEARCH_OFFLINE = (
    "You're offline, so scans can't reach sites. Check your connection and try again."
)
