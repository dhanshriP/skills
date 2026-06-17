"""Web search for candidate solutions.

Uses Google's Programmable Search / Custom Search JSON API (the supported way —
scraping google.com directly is against ToS and brittle).

Env: GOOGLE_CSE_KEY, GOOGLE_CSE_ID.
Degrades gracefully: is_configured() lets the caller fall back to LLM-only
suggestions, clearly labelled as ungrounded.
"""
import os
import requests


def is_configured() -> bool:
return bool(os.environ.get("GOOGLE_CSE_KEY") and os.environ.get("GOOGLE_CSE_ID"))


def search(query: str, num: int = 6):
key = os.environ["GOOGLE_CSE_KEY"]
cx = os.environ["GOOGLE_CSE_ID"]
r = requests.get(
"https://www.googleapis.com/customsearch/v1",
params={"key": key, "cx": cx, "q": query, "num": min(num, 10)},
timeout=20,
)
r.raise_for_status()
items = r.json().get("items", [])
return [{"title": i.get("title", ""), "link": i.get("link", ""),
"snippet": i.get("snippet", "")} for i in items]
