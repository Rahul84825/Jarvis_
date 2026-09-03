# Browser Search & Navigation Commands Manual

## Overview
Jarvis interprets natural spoken voice phrases for web search across Google, YouTube, GitHub, Reddit, and Stack Overflow, as well as website shortcut launching.

---

## Command Reference Matrix

| Spoken Voice Command | Recognized Intent | Provider | Query / Target | Spoken Confirmation Output |
|---|---|---|---|---|
| *"Search Google for Python tutorials"* | `web_search` | Google | `python tutorials` | `"Searching Google."` |
| *"Google Python tutorials"* | `web_search` | Google | `python tutorials` | `"Searching Google."` |
| *"Search Chrome for React tutorials"* | `web_search` | Google | `react tutorials` | `"Searching Google."` |
| *"Look up Python decorators"* | `web_search` | Google | `python decorators` | `"Searching Google."` |
| *"Search YouTube for CodeWithHarry"* | `web_search` | YouTube | `codewithharry` | `"Searching YouTube."` |
| *"Find Minecraft shaders on YouTube"* | `web_search` | YouTube | `minecraft shaders` | `"Searching YouTube."` |
| *"Search GitHub for React dashboards"* | `web_search` | GitHub | `react dashboards` | `"Searching GitHub."` |
| *"Search Reddit for Linux gaming"* | `web_search` | Reddit | `linux gaming` | `"Searching Reddit."` |
| *"Search Stack Overflow for recursion"* | `web_search` | Stack Overflow | `recursion` | `"Searching Stack Overflow."` |
| *"Open YouTube"* | `open_website` | N/A | `youtube` | `"Opening YouTube."` |
| *"Open GitHub"* | `open_website` | N/A | `github` | `"Opening GitHub."` |

---

## Multi-Command Chains

- *"Open Chrome and search Google for Python"* -> 1. `open_app -> chrome`, 2. `web_search -> google (python)`
- *"Open YouTube and search for Minecraft tutorials"* -> 1. `open_website -> youtube`, 2. `web_search -> youtube (minecraft tutorials)`
