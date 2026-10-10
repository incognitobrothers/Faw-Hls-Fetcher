
import os
import re
import html
import json
import tempfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = os.environ.get("BASE_URL", "").strip()

if not BASE_URL:
    raise RuntimeError("GitHub Secret BASE_URL is not configured.")

if not urlparse(BASE_URL).scheme:
    BASE_URL = "https://" + BASE_URL

BASE_URL = BASE_URL.rstrip("/") + "/"
BASE_PARSED = urlparse(BASE_URL)

if BASE_PARSED.scheme not in ("http", "https") or not BASE_PARSED.netloc:
    raise RuntimeError("BASE_URL is invalid.")

ORIGIN = f"{BASE_PARSED.scheme}://{BASE_PARSED.netloc}"
REFERER = BASE_URL

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

EVENTS_FILE = "events.json"
PLAYLIST_FILE = "playlist.m3u"

EVENT_LOGO = (
    "https://i.ibb.co/dwgyr6t4/live.jpg"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "Origin": ORIGIN,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def load_events():
    """Load the saved events without storing page URLs."""
    if not os.path.exists(EVENTS_FILE):
        return {}

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Support both the current list and older dictionary format.
        if isinstance(data, dict):
            data = data.get("events", [])

        if not isinstance(data, list):
            return {}

        saved = {}

        for item in data:
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("title")
            if not name:
                continue

            key = name.strip().casefold()

            saved[key] = {
                "name": name,
                "m3u": item.get("m3u") or item.get("url"),
                "user_agent": USER_AGENT,
                "referer": REFERER,
                "origin": ORIGIN,
            }

        return saved

    except (OSError, json.JSONDecodeError) as error:
        print(f"DATABASE ERROR: {error}")
        raise


def save_events(events):
    """Save only the five requested fields."""
    data = []

    for item in events.values():
        data.append({
            "name": item["name"],
            "m3u": item.get("m3u"),
            "user_agent": USER_AGENT,
            "referer": REFERER,
            "origin": ORIGIN,
        })

    directory = os.path.dirname(os.path.abspath(EVENTS_FILE))
    fd, temp_path = tempfile.mkstemp(
        prefix="events_",
        suffix=".tmp",
        dir=directory,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

        os.replace(temp_path, EVENTS_FILE)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def get_all_event_links(session):
    response = session.get(
        BASE_URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen = set()

    for card in soup.select(".user-item"):
        name_element = card.select_one(".user-item__name")
        playing_element = card.select_one(".user-item__playing")
        link_element = card.select_one("a[href]")

        if not name_element or not link_element:
            continue

        title = html.unescape(
            name_element.get_text(" ", strip=True)
        ).strip()

        playing = (
            playing_element.get_text(" ", strip=True)
            if playing_element else ""
        )

        if not title:
            continue

        page_url = urljoin(BASE_URL, link_element["href"])
        parsed = urlparse(page_url)

        if (
            parsed.scheme not in ("http", "https")
            or parsed.netloc.lower() != BASE_PARSED.netloc.lower()
        ):
            continue

        key = title.casefold()

        if key in seen:
            continue

        seen.add(key)

        results.append({
            "name": title.upper(),
            "playing": playing,
            "page_url": page_url,
        })

    return results


def extract_m3u8(session, page_url):
    try:
        response = session.get(
            page_url,
            headers={**HEADERS, "Referer": REFERER},
            timeout=30,
        )
        response.raise_for_status()
        page_html = response.text

        d1 = re.search(
            r"""var\s+d1\s*=\s*["']([^"']+)["']""",
            page_html,
        )
        d2 = re.search(
            r"""var\s+d2\s*=\s*["']([^"']+)["']""",
            page_html,
        )
        d3 = re.search(
            r"""var\s+d3\s*=\s*["']([^"']+)["']""",
            page_html,
        )

        if d1 and d2 and d3:
            stream_url = html.unescape(
                d1.group(1) + d2.group(1) + d3.group(1)
            )
        else:
            match = re.search(
                r"""https?://[^\s"'<>\\]+\.m3u8(?:\?[^\s"'<>]*)?""",
                page_html,
                re.IGNORECASE,
            )

            if not match:
                return None

            stream_url = html.unescape(match.group(0))

        parsed = urlparse(stream_url)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or not parsed.path.lower().endswith(".m3u8")
        ):
            return None

        return stream_url

    except requests.RequestException as error:
        print(f"STREAM PAGE ERROR: {error}")
        return None


def build_m3u(events):
    unique_items = []
    seen_urls = set()

    for item in events.values():
        stream_url = item.get("m3u")

        if not stream_url or stream_url in seen_urls:
            continue

        seen_urls.add(stream_url)
        unique_items.append(item)

    directory = os.path.dirname(os.path.abspath(PLAYLIST_FILE))
    fd, temp_path = tempfile.mkstemp(
        prefix="playlist_",
        suffix=".tmp",
        dir=directory,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write("#EXTM3U\n")

            for item in unique_items:
                title = (
                    item["name"]
                    .replace('"', "'")
                    .replace("\r", " ")
                    .replace("\n", " ")
                )

                file.write(
                    f'#EXTINF:-1 tvg-name="{title}" '
                    f'tvg-logo="{EVENT_LOGO}" '
                    f'group-title="LIVE EVENTS",{title}\n'
                )

                file.write(f"#EXTVLCOPT:http-referrer={REFERER}\n")
                file.write(f"#EXTVLCOPT:http-origin={ORIGIN}\n")
                file.write(f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n")

                file.write(
                    "#EXTHTTP:"
                    + json.dumps({
                        "referer": REFERER,
                        "origin": ORIGIN,
                        "user-agent": USER_AGENT,
                    })
                    + "\n"
                )

                file.write(item["m3u"] + "\n\n")

        os.replace(temp_path, PLAYLIST_FILE)
        temp_path = None

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    print(f"Playlist saved: {PLAYLIST_FILE}")
    print(f"Unique streams: {len(unique_items)}")


def main():
    events = load_events()

    with requests.Session() as session:
        # If the homepage fails, don't overwrite the old playlist.
        matches = get_all_event_links(session)

        print(f"Events found: {len(matches)}")

        for index, match in enumerate(matches, start=1):
            name = match["name"]
            key = name.casefold()
            page_url = match["page_url"]

            print(f"[{index}/{len(matches)}] Checking: {name}")

            item = events.get(key, {
                "name": name,
                "m3u": None,
                "user_agent": USER_AGENT,
                "referer": REFERER,
                "origin": ORIGIN,
            })

            item["name"] = name
            item["user_agent"] = USER_AGENT
            item["referer"] = REFERER
            item["origin"] = ORIGIN

            try:
                stream_url = extract_m3u8(session, page_url)

                if stream_url:
                    item["m3u"] = stream_url
                    print("STREAM FOUND / UPDATED")
                else:
                    print("STREAM NOT FOUND; retaining old URL if available")

            except requests.RequestException as error:
                print(f"EVENT ERROR: {error}")

            events[key] = item

            # Persist progress after each event.
            save_events(events)

    # Keep previously saved events even when absent from this homepage.
    build_m3u(events)
    print(f"Database saved: {EVENTS_FILE}")
    print(f"Total stored events: {len(events)}")


if __name__ == "__main__":
    main()
