# Sherlock Release Notes

All notable changes to Sherlock are documented here.

---

## v1.3.0

**Build:** 5
**Released:** August 5, 2026

### 🏗️ Architecture Rewrite

- **React-Style Component System** — Migrated from imperative `page.views` manipulation to `@ft.component` with hooks (`use_state`, `use_context`, `use_effect`, `use_memo`).
- **Observable State** — `@ft.observable` AppState singleton with `create_context` providers. Components auto-subscribe and re-render selectively — only the affected screen updates.
- **AppShell Pattern** — Single root View with `use_state` branching: onboarding → results → sites → dashboard (Home/History/Settings tabs).
- **ControllerMethods Context** — Mutable dataclass of no-op defaults, populated by AppController and extended by AppShell with view-local closures.

### 🎨 Design System (Sherlock × DDGS)

- **Gold Brand Colors** — Primary `#A68E59` (Khaki-Gold from logo), accent `#CD995F` (Caramel-Gold). Replaced previous indigo scheme.
- **DDGS Glass Pattern** — `adaptive_glass_bg/border` helpers for premium frosted-glass cards that adapt to dark/light.
- **53 Design Tokens** — Typography, spacing, radii, icon sizes, animation durations, opacity levels, elevation, and component dimensions.
- **Pure Black Text** — `#000000` in light mode for maximum contrast. `#424242` for secondary text.

### 🔍 Home Screen (DDGS-Style)

- **Modern SearchBar** — Full-screen `ft.SearchBar` replacing the old `ft.TextField`.
- **Category Chips** — Real Sherlock settings: Timeout, Offline DB, NSFW, Exclusions.
- **Expandable Search Tools** — Dropdown panel for timeout and offline DB configuration.
- **Feature Cards** — "What Sherlock Can Do" section with 3 highlight rows.
- **How It Works** — Numbered 3-step guide (Enter → Scan → Done).
- **Trust Banner** — "100% Privacy-First" branded banner at bottom.

### 📊 Results Screen

- **Live Progress** — Observable `progress_version` bump triggers selective re-render on each search tick.
- **Virtualized Tabs** — Found/Not Found/Errors with `ListView` for 400+ result items.
- **Debounced Filter** — 250ms debounced search filter on results.
- **AppBar Actions** — Copy URLs, Export (Excel/CSV/Text dialog), Search Again.

### ⚙️ Settings & Screens

- **Grouped Settings Cards** — `_settings_card` + `_setting_row` factories for modern Material 3 layout.
- **Reactive History** — Reads `state.history` directly (Observable auto-triggers re-render).
- **Theme Persistence** — Toggle saves to `STORAGE_THEME` — preference survives restart.
- **Theme Toggle** — Cycles: Dark → Light → System. Forces full re-render on toggle.

### 🧪 Testing

- **Test Suite** — 6 test suites: state (observable), services (parse_usernames, SearchProgress), components (tree-walk), component smoke, controller_ctx, app_state_ctx.
- **Flet Tree Walkers** — `flet_tree.py` helpers ported from KTV Player for component inspection.
- **FakePage Fixture** — Mock page for controller testing.

### 📦 Infrastructure

- **New Module Structure** — `src/components/`, `src/screens/`, `src/state/`, `src/hooks/`.
- **34 Verified Icons** — All `ft.Icons.*` references verified against Flet 0.85.0 source.
- **Ruff Clean** — Zero lint errors across all source and test files.
- **Old `src/views/` Deleted** — Replaced by `src/screens/` with `@ft.component` screens.

---

## v1.2.1 (Current)

**Build:** 4  
**Released:** July 27, 2026

### 🐛 Bug Fixes

- **Multi-Username Search Fix** — Fixed a bug where scanning multiple usernames at once could produce incorrect results due to a variable capture issue in the search loop.
- **Export Freeze Fix** — Report downloads on desktop no longer freeze the app UI while writing the file.
- **Stability Improvements** — Resolved several internal state management issues that could cause unexpected behavior during searches.

---

## v1.2.0

**Released:** June 8, 2026

### 🗑️ Removed

- **🔒 Tor Privacy Routing Removed**
  - Tor & Unique Tor toggles removed from Settings — these options caused crashes on mobile when toggled.
  - Proxy input removed — was grouped in the same networking section.
  - All Tor/proxy error dialogs removed — simplified connection error handling.
  - Tor/Unique Tor/proxy params stripped from the Sherlock search invocation.

### 🐛 Bug Fixes & Stability

- **Settings & Download Crash Fixes** — Swapped outdated components to resolve crashes during dropdown selection, settings changes, and report downloads.
- **Tor/Proxy Toggle Crashes Fixed** — Removed the entire Advanced Proxy & Tor section from Settings, which caused the app to crash on mobile when toggled.
- **Alert Delivery Fixes** — Solved a race condition that caused error dialogues to occasionally get swallowed during page transitions.

---

## v1.1.0

**Released:** June 5, 2026

### 🌟 What's New

- **🔒 Tor Privacy Routing**
  - Tor & Unique Tor Support: Route queries through the Tor network (Orbot on Android, or local Tor daemon) for anonymous searches.
  - Tor Connectivity Warnings: Automatic alerts if Tor is enabled but no service is active.

- **📊 Excel Reports & Multi-Format Exports**
  - Excel (.xlsx) Downloads: Save scan results in fully formatted Excel spreadsheets.
  - Additional Formats: Export as PDF, HTML, JSON, and CSV directly to your device.

- **⚙️ Target Customization & Database Sync**
  - Select Networks: Choose specific social networks to scan from 400+ supported sites.
  - GitHub Sync: Synchronize target databases with the official Sherlock repository.

- **👥 Multi-Username & Wildcard Searches**
  - Bulk Searches: Scan multiple usernames at once (comma or space-separated).
  - Wildcard Expanders: Use `{?}` to automatically scan username variations (`user.`, `user_`, `user-`).

- **📱 Spacing & Mobile Viewport Redesign**
  - Compact Home View: Optimized layout fits on mobile screens without scrolling.

- **🎨 Theme Support**
  - Quick Theme Toggle: Switch between Solarized Light and Monokai Dark themes.

### 🐛 Bug Fixes & Stability

- Settings & Download Crash Fixes
- Smart Connection Diagnostics
- Direct Settings Shortcuts in error alerts
- Alert Delivery race condition fixes

---

## v1.0.0

**Released:** May 28, 2026

### 🚀 Initial Release

A user-friendly interface for the open-source Sherlock Project — making its powerful OSINT engine accessible to everyone. No terminal required.

### Features

- **400+ Social Networks** — Searches across the largest collection of social media platforms, forums, and websites.
- **Live Progress** — Watch results appear in real-time. Found / Not Found / Error tabs.
- **Profile Links** — Tap any found account to open the profile in your browser.
- **Search History** — Every search saved locally. Re-run with one tap.
- **Privacy-First** — All searches run directly from your device. No servers, no accounts.
- **Dark & Light Mode** — System-aware theme.
- **Export Reports** — TXT, CSV, and Excel formats.

### Acknowledgments

Built on top of the [Sherlock Project](https://github.com/sherlock-project/sherlock) by sdushantha and contributors.
