import json
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional

logger = logging.getLogger("Jarvis.WebIntel")

class WebIntelligence:
    """Real-Time Web Intelligence, Live Search, News Aggregator, and Weather Engine.
    Operates without requiring paid API keys, utilizing open search endpoints and RSS feeds.
    """

    RSS_FEEDS = {
        "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "tech": "https://feeds.feedburner.com/TechCrunch/",
        "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"
    }

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def search_web(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Performs a live web search using DuckDuckGo HTML / JSON endpoints."""
        clean_query = query.strip()
        logger.info(f"Executing web search for query: '{clean_query}'")
        results = []

        try:
            # First try DuckDuckGo instant answer JSON API
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Check abstract
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", "Instant Answer"),
                        "snippet": data.get("AbstractText"),
                        "url": data.get("AbstractURL", "")
                    })
                
                # Related topics
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and "Text" in topic:
                        results.append({
                            "title": topic.get("Text", "").split(" - ")[0],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", "")
                        })

            # If DuckDuckGo instant answer had sparse results, scrape DDG HTML lite
            if len(results) < 2:
                html_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_query)}"
                req2 = urllib.request.Request(html_url, headers=self.headers)
                with urllib.request.urlopen(req2, timeout=5) as resp:
                    html = resp.read().decode('utf-8', errors='ignore')
                    # Parse snippets
                    from html.parser import HTMLParser
                    class DDGParser(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.in_snippet = False
                            self.current_snippet = []
                            self.snippets = []

                        def handle_starttag(self, tag, attrs):
                            attrs_dict = dict(attrs)
                            if tag == 'a' and 'result__snippet' in attrs_dict.get('class', ''):
                                self.in_snippet = True
                                self.current_snippet = []

                        def handle_endtag(self, tag):
                            if tag == 'a' and self.in_snippet:
                                self.in_snippet = False
                                text = " ".join(self.current_snippet).strip()
                                if text:
                                    self.snippets.append(text)

                        def handle_data(self, data):
                            if self.in_snippet:
                                self.current_snippet.append(data)

                    parser = DDGParser()
                    parser.feed(html)
                    for snip in parser.snippets[:max_results]:
                        results.append({
                            "title": f"Web Result for {clean_query}",
                            "snippet": snip,
                            "url": ""
                        })
        except Exception as e:
            logger.error(f"Error executing web search: {e}")

        logger.info(f"Web search returned {len(results)} results.")
        return results

    def get_live_news(self, category: str = "world", limit: int = 5) -> List[Dict[str, str]]:
        """Fetches live breaking news headlines from verified RSS feeds."""
        category_clean = category.lower().strip()
        feed_url = self.RSS_FEEDS.get(category_clean, self.RSS_FEEDS["world"])
        
        logger.info(f"Fetching live news for category '{category_clean}' from {feed_url}")
        headlines = []

        try:
            req = urllib.request.Request(feed_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                xml_data = resp.read()
                root = ET.fromstring(xml_data)

                # Standard RSS 2.0 item parsing
                for item in root.findall(".//item")[:limit]:
                    title = item.findtext("title", "").strip()
                    desc = item.findtext("description", "").strip()
                    link = item.findtext("link", "").strip()
                    pub_date = item.findtext("pubDate", "").strip()

                    # Clean CDATA or HTML tags in description
                    desc_clean = desc.split("<")[0].strip() if "<" in desc else desc

                    if title:
                        headlines.append({
                            "title": title,
                            "summary": desc_clean,
                            "link": link,
                            "date": pub_date
                        })
        except Exception as e:
            logger.error(f"Error fetching RSS news: {e}")

        logger.info(f"Retrieved {len(headlines)} news articles.")
        return headlines

    def get_weather(self, city: str = "") -> Dict[str, Any]:
        """Fetches live weather conditions via wttr.in JSON API without requiring an API key."""
        target_city = urllib.parse.quote(city.strip()) if city else ""
        url = f"https://wttr.in/{target_city}?format=j1"

        logger.info(f"Fetching weather telemetry from {url}")
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                current = data["current_condition"][0]
                area = data["nearest_area"][0]
                location_name = area["areaName"][0]["value"]
                country = area["country"][0]["value"]

                return {
                    "success": True,
                    "location": f"{location_name}, {country}",
                    "temp_c": current["temp_C"],
                    "temp_f": current["temp_F"],
                    "condition": current["weatherDesc"][0]["value"],
                    "humidity": current["humidity"],
                    "wind_speed_kmh": current["windspeedKmph"],
                    "formatted": f"Weather in {location_name}: {current['weatherDesc'][0]['value']}, {current['temp_C']}°C (Feels like {current['FeelsLikeC']}°C) with {current['humidity']}% humidity."
                }
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return {
                "success": False,
                "message": f"Unable to fetch weather data: {str(e)}"
            }

    def generate_morning_briefing(self, city: str = "") -> str:
        """Generates a rich, natural morning briefing combining weather and top headlines."""
        weather_info = self.get_weather(city)
        news_items = self.get_live_news(category="world", limit=3)

        briefing_parts = ["Good morning! Here is your daily intelligence briefing."]

        if weather_info.get("success"):
            briefing_parts.append(weather_info["formatted"])

        if news_items:
            briefing_parts.append("Here are today's top headlines:")
            for i, n in enumerate(news_items, 1):
                briefing_parts.append(f"{i}. {n['title']}.")

        briefing_parts.append("All primary systems are active and ready for your command.")
        return " ".join(briefing_parts)

# Singleton instance
web_intel = WebIntelligence()
