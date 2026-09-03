# Browser Subsystem Configuration Guide

## Overview
Jarvis browser preferences and search provider endpoints are managed via lightweight JSON configuration files in `config/`.

---

## 1. Browser Preference (`config/browser.json`)

```json
{
  "preferred_browser": "chrome",
  "fallback_browser": true
}
```

- `preferred_browser`: Target browser (`"chrome"`, `"chromium"`, `"edge"`, `"firefox"`, `"default"`).
- `fallback_browser`: If `true`, falls back to available browsers (`Chrome` -> `Chromium` -> `Default Browser`) if preferred browser is missing. If `false`, returns a clean error when preferred browser is missing.

---

## 2. Search Providers Registry (`config/search_providers.json`)

```json
{
  "google": { "base_url": "https://www.google.com/search?q={query}" },
  "youtube": { "base_url": "https://www.youtube.com/results?search_query={query}" },
  "github": { "base_url": "https://github.com/search?q={query}" },
  "reddit": { "base_url": "https://www.reddit.com/search/?q={query}" },
  "stackoverflow": { "base_url": "https://stackoverflow.com/search?q={query}" }
}
```

---

## 3. Website Registry (`config/links.json`)

```json
{
  "google": "https://www.google.com",
  "youtube": "https://www.youtube.com",
  "github": "https://github.com",
  "gmail": "https://mail.google.com",
  "drive": "https://drive.google.com",
  "calendar": "https://calendar.google.com",
  "spotify": "https://open.spotify.com",
  "reddit": "https://www.reddit.com",
  "stackoverflow": "https://stackoverflow.com"
}
```
