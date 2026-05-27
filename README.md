<p align="center">
  <img src="src/assets/logo.png" alt="Sherlock" width="140" />
</p>

<h1 align="center">Sherlock</h1>

<p align="center">
  Hunt down social media accounts by username across 400+ networks. Built with Python and Flet.
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
| 🤖 **Android (Universal)** | [**sherlock.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock.apk) | Works on all Android devices (ARM64, ARMv7, x86_64) |
| 🤖 **Android (ARM64)** | [**sherlock-arm64-v8a.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-arm64-v8a.apk) | For modern 64-bit Android devices |
| 🤖 **Android (ARM32)** | [**sherlock-armeabi-v7a.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-armeabi-v7a.apk) | For older 32-bit Android devices |
| 🤖 **Android (x86_64)** | [**sherlock-x86_64.apk**](https://github.com/Nwokike/Sherlock/releases/latest/download/sherlock-x86_64.apk) | For Android emulators / ChromeOS |
| 🪟 **Windows** | [**Sherlock_Setup.exe**](https://github.com/Nwokike/Sherlock/releases/latest/download/Sherlock_Setup.exe) | Windows 10/11 Installer (64-bit) |

---

## Features

- **400+ Social Networks** — Searches across the largest collection of social media platforms, forums, and websites.
- **Live Progress** — Watch results appear in real-time as each network is checked. Found/Not Found/Error tabs.
- **Smart Detection** — Uses multiple detection methods (status code, response message, URL redirect) for maximum accuracy.
- **Profile Links** — Tap any found account to open the profile in your browser instantly.
- **Search History** — Every search is saved locally. Re-run any previous search with one tap.
- **Privacy-First** — All searches run directly from your device. No servers, no tracking, no accounts.
- **Dark/Light Mode** — System-aware theme with premium color palette.
- **NSFW Filtering** — NSFW sites are excluded by default for safe searching.

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Flet (Python → Flutter) |
| Search Engine | `sherlock-project` — 400+ site username detection engine |
| Network | `httpx` (async, connection pooling, limits) |
| Storage | JSON files (persistent settings and search history) |
| Ads | `flet-ads` (AdMob banner + interstitial) |

## Credits

Powered by the [Sherlock Project](https://github.com/sherlock-project/sherlock) — an open-source tool for finding social media accounts by username across social networks.

## Legal Disclaimer

Sherlock is an OSINT tool for finding public social media profiles by username. It only checks publicly accessible information. Users are solely responsible for complying with applicable laws and terms of service of the platforms they search.
