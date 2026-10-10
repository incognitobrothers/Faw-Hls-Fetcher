
import requests
import re
import html
import json
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

BASE_URL = "http://www.fawanews.sc/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

REFERER = BASE_URL
ORIGIN = BASE_URL.rstrip("/")

EVENTS_FILE = "events.json"
PLAYLIST_FILE = "playlist.m3u"
LOGO = (
    "https://upload.wikimedia.org/wikipedia/commons/8/89/Cricket_ball.svg"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "Origin": ORIGIN,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def load_events():
    """আগের event database লোড করবে।"""
    if not os.path.exists(EVENTS_FILE):
        return {}

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # নতুন dictionary format অথবা পুরোনো list format গ্রহণ করবে।
        if isinstance(data, dict):
            events = data.get("events", {})
            if isinstance(events, dict):
                return events

        if isinstance(data, list):
            return {
                item["page"]: item
                for item in data
                if isinstance(item, dict) and item.get("page")
            }

    except (json.JSONDecodeError, OSError) as error:
        print(f"DATABASE READ ERROR: {error}")

    return {}


def save_events(events):
    """Atomic write ব্যবহার করে database সেভ করবে।"""
    data = {
        "updated_at": now_utc(),
        "events": events,
    }

    directory = os.path.dirname(os.path.abspath(EVENTS_FILE))

    fd, temp_path = tempfile.mkstemp(
        prefix="events_",
        suffix=".tmp",
        dir=directory,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, EVENTS_FILE)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def is_valid_event(title, playing):
    return bool((title or "").strip() or (playing or "").strip())


def get_all_match_links(session):
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

        if not name_element:
            continue

        title = html.unescape(
            name_element.get_text(" ", strip=True)
        ).strip()

        playing = (
            playing_element.get_text(" ", strip=True)
            if playing_element else ""
        )

        if not is_valid_event(title, playing):
            continue

        link_element = card.select_one("a[href]")

        if not link_element:
            continue

        page_url = urljoin(BASE_URL, link_element["href"])
        parsed = urlparse(page_url)

        if (
            parsed.scheme not in ("http", "https")
            or parsed.netloc.lower() != urlparse(BASE_URL).netloc.lower()
        ):
            continue

        if page_url in seen:
            continue

        seen.add(page_url)

        results.append({
            "title": title.upper(),
            "playing": playing,
            "page": page_url,
        })

    return results


def extract_m3u8(session, page_url):
    try:
        response = session.get(
            page_url,
            headers={**HEADERS, "Referer": BASE_URL},
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
            stream_url = (
                d1.group(1) + d2.group(1) + d3.group(1)
            )
            stream_url = html.unescape(stream_url)

        else:
            match = re.search(
                r"""https?://[^\s"'<>\\]+\.m3u8(?:\?[^\s"'<>]*)?""",
                page_html,
                re.IGNORECASE,
            )

            if not match:
                print(f"NO STREAM: {page_url}")
                return None

            stream_url = html.unescape(match.group(0))

        parsed = urlparse(stream_url)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or not parsed.path.lower().endswith(".m3u8")
        ):
            print(f"INVALID STREAM URL: {page_url}")
            return None

        return stream_url

    except requests.RequestException as error:
        print(f"PAGE ERROR: {page_url} - {error}")
        return None


def build_m3u(events, out_file=PLAYLIST_FILE):
    """Database-এর বর্তমানে পাওয়া stream দিয়ে playlist তৈরি করবে।"""
    unique_items = []
    seen_streams = set()

    for page_url, event in events.items():
        stream_url = event.get("url")

        if not stream_url:
            continue

        if stream_url in seen_streams:
            continue

        seen_streams.add(stream_url)

        unique_items.append({
            "title": event.get("title", "LIVE EVENT"),
            "url": stream_url,
        })

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=os.path.dirname(os.path.abspath(out_file)),
            suffix=".tmp",
        ) as f:
            temp_path = f.name
            f.write("#EXTM3U\n")

            for item in unique_items:
                title = (
                    item["title"]
                    .replace('"', "'")
                    .replace("\r", " ")
                    .replace("\n", " ")
                )

                f.write(
                    f'#EXTINF:-1 tvg-name="{title}" '
                    f'tvg-logo="{LOGO}" '
                    f'group-title="LIVE EVENTS",{title}\n'
                )

                f.write(f"#EXTVLCOPT:http-referrer={REFERER}\n")
                f.write(f"#EXTVLCOPT:http-origin={ORIGIN}\n")
                f.write(f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n")

                headers_json = json.dumps({
                    "referer": REFERER,
                    "origin": ORIGIN,
                    "user-agent": USER_AGENT,
                })

                f.write(f"#EXTHTTP:{headers_json}\n")
                f.write(item["url"] + "\n\n")

        os.replace(temp_path, out_file)
        temp_path = None

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    print(f"Playlist saved: {out_file}")
    print(f"Total unique streams: {len(unique_items)}")


def main():
    events = load_events()
    print(f"Previously saved events: {len(events)}")

    with requests.Session() as session:
        try:
            matches = get_all_match_links(session)

        except requests.RequestException as error:
            print(f"HOMEPAGE ERROR: {error}")
            # Homepage ব্যর্থ হলে পুরোনো database ও playlist
            # অক্ষত রাখবে; খালি playlist তৈরি করবে না।
            raise

        print(f"Events found on homepage: {len(matches)}")

        # প্রথমে সব পাওয়া event database-এ যোগ করবে।
        for match in matches:
            page_url = match["page"]

            if page_url not in events:
                events[page_url] = {
                    "title": match["title"],
                    "playing": match["playing"],
                    "page": page_url,
                    "url": None,
                    "first_seen": now_utc(),
                    "last_checked": None,
                }
            else:
                events[page_url]["title"] = match["title"]
                events[page_url]["playing"] = match["playing"]

        # নতুন event-গুলোর তথ্য আগে সংরক্ষণ করবে।
        save_events(events)

        # সব পুরোনো এবং নতুন event-এর stream পুনরায় পরীক্ষা করবে।
        total = len(events)

        for index, (page_url, event) in enumerate(
            list(events.items()), start=1
        ):
            print(f"\n[{index}/{total}] {event.get('title', page_url)}")

            event["last_checked"] = now_utc()

            try:
                stream_url = extract_m3u8(session, page_url)

                if stream_url:
                    event["url"] = stream_url
                    event["last_stream_found"] = now_utc()
                    print("STREAM UPDATED")
                else:
                    # নতুন stream না পেলে আগের URL মুছবে না।
                    print("STREAM NOT FOUND; keeping previous URL")

            except Exception as error:
                print(f"EVENT ERROR: {error}")

            # প্রতিটি event-এর পর progress সংরক্ষণ করবে।
            save_events(events)

        build_m3u(events)

        print(f"\nDatabase saved: {EVENTS_FILE}")
        print(f"Total stored events: {len(events)}")


if __name__ == "__main__":
    main()
