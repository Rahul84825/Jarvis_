# JARVIS ASSISTANT - SUPPORTED WEBSITES REFERENCE

This document lists all pre-configured web links supported by Jarvis AI Assistant via the configurable web link engine ([config/links.json](file:///c:/Users/activ/OneDrive/Attachments/Desktop/jarvis/config/links.json)).

---

## Configuration Location
Web links are loaded dynamically from:
`config/links.json`

Users can add custom site shortcuts to `config/links.json` without modifying any code files.

---

## Pre-Configured Websites (20+ Sites)

| Site Name / Voice Target | Resolved Web URL | Category |
| :--- | :--- | :--- |
| `youtube` | `https://www.youtube.com` | Media & Video |
| `google` | `https://www.google.com` | Search |
| `github` | `https://www.github.com` | Developer & Code |
| `gmail` | `https://mail.google.com` | Email & Productivity |
| `chatgpt` | `https://chatgpt.com` | AI Assistant |
| `claude` | `https://claude.ai` | AI Assistant |
| `gemini` | `https://gemini.google.com` | AI Assistant |
| `spotify` | `https://open.spotify.com` | Music & Audio |
| `netflix` | `https://www.netflix.com` | Media & Video |
| `prime video` / `primevideo` | `https://www.primevideo.com` | Media & Video |
| `discord` | `https://discord.com/app` | Social & Chat |
| `reddit` | `https://www.reddit.com` | Social & Community |
| `stack overflow` / `stackoverflow` | `https://stackoverflow.com` | Developer QA |
| `linkedin` | `https://www.linkedin.com` | Professional |
| `instagram` | `https://www.instagram.com` | Social Media |
| `facebook` | `https://www.facebook.com` | Social Media |
| `x` / `twitter` | `https://x.com` | Social Media |
| `whatsapp` / `whatsapp web` | `https://web.whatsapp.com` | Social & Messaging |
| `google drive` / `drive` | `https://drive.google.com` | Cloud Storage |
| `google calendar` / `calendar` | `https://calendar.google.com` | Productivity & Calendar |

---

## Adding Custom Websites

To add a new site, open `config/links.json` and add a new entry:

```json
{
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com"
}
```

Saying **"Open Notion"** or **"Open Figma"** will automatically resolve and launch the website in your default browser.
