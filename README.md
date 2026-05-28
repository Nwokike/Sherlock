<p align="center">
  <img src="src/assets/icon.png" alt="Sherlock" width="140" />
</p>

<h1 align="center">Sherlock</h1>

<p align="center">
  A user-friendly interface for the <a href="https://github.com/sherlock-project/sherlock">Sherlock Project</a> — making its powerful OSINT engine accessible to everyone. No terminal required.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Android-3DDC84?style=flat-square&logo=android&logoColor=white" alt="Android" />
  <img src="https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows11&logoColor=white" alt="Windows" />
  <br>
  <img src="https://img.shields.io/badge/Built%20with-Flet%200.85-00B0FF?style=flat-square" alt="Built with Flet" />
</p>

---

## Download

| Platform | Download | Notes |
|:--------:|:--------:|:------|
| 🤖 **Android (ARM64)** | [**sherlock-arm64-v8a.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-arm64-v8a.apk) | For most modern Android devices |
| 🤖 **Android (ARM32)** | [**sherlock-armeabi-v7a.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-armeabi-v7a.apk) | For older 32-bit Android devices |
| 🤖 **Android (x86_64)** | [**sherlock-x86_64.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-x86_64.apk) | For Android emulators / ChromeOS |
| 🪟 **Windows** | [**Sherlock_Setup.exe**](https://github.com/Nwokike/Sherlock/releases/latest/download/Sherlock_Setup.exe) | Windows 10/11 Installer (64-bit) |

---

## Screenshots

> 🖼️ Place screenshots in the `screenshots/` directory and reference them below.

### Mobile Experience

<table>
  <tr>
    <td width="50%"><img src="screenshots/home_dark.png" width="100%" alt="Home Screen" /></td>
    <td width="50%"><img src="screenshots/results_light.png" width="100%" alt="Search Results" /></td>
  </tr>
  <tr>
    <td align="center"><em>Home screen — enter a username to search across 400+ networks</em></td>
    <td align="center"><em>Live search results with Found/Not Found/Error tabs</em></td>
  </tr>
</table>

<table>
  <tr>
    <td width="50%"><img src="screenshots/export_menu.png" width="100%" alt="Export Menu" /></td>
    <td width="50%"><img src="screenshots/settings_dark.png" width="100%" alt="Settings" /></td>
  </tr>
  <tr>
    <td align="center"><em>Export report to TXT, CSV, or XLSX</em></td>
    <td align="center"><em>Settings — dark mode, export preferences, and more</em></td>
  </tr>
</table>

---

## Features

- **400+ Social Networks** — Searches across the largest collection of social media platforms, forums, and websites.
- **Live Progress** — Watch results appear in real-time as each network is checked. Found/Not Found/Error tabs.
- **Smart Detection** — Uses multiple detection methods (status code, response message, URL redirect) for maximum accuracy.
- **Profile Links** — Tap any found account to open the profile in your browser instantly.
- **Search History** — Every search is saved locally. Re-run any previous search with one tap.
- **Privacy-First** — All searches run directly from your device. No servers, no tracking, no accounts.
- **Dark/Light Mode** — System-aware theme with premium color palette.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Flet (Python → Flutter) — cross-platform UI |
| Search Engine | [sherlock-project](https://github.com/sherlock-project/sherlock) — 400+ site detection engine |
| Network | `httpx` (async, connection pooling, limits) |
| Storage | JSON files (persistent settings and search history) |

## Legal Disclaimer

Sherlock is an OSINT tool for finding public social media profiles by username. It only checks publicly accessible information. Users are solely responsible for complying with applicable laws and terms of service of the platforms they search.
