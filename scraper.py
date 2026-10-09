import requests
import re
import html
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

CRICKET_LOGO = (
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


def is_cricket_event(title, playing):
    """
    Homepage-এর event category দেখে cricket match শনাক্ত করে।
    """
    title = (title or "").strip()
    playing = (playing or "").strip()

    # Explicit cricket category থাকলেই গ্রহণ করবে।
    if re.search(r"\bcricket\b", playing, re.IGNORECASE):
        return True

    # অন্য sport হলে বাদ।
    if re.search(
        r"\b(football|soccer|basketball|tennis|badminton|"
        r"volleyball|rugby|hockey|baseball|golf|boxing|"
        r"mma|ufc|motogp|darts|horse racing)\b",
        playing,
        re.IGNORECASE,
    ):
        return False

    # শুধু দুই দলের নাম বা VS দেখে ক্রিকেট অনুমান করবে না।
    return False


def get_cricket_links():
    response = requests.get(
        BASE_URL,
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    seen = set()

    for card in soup.select(".user-item"):
        name_element = card.select_one(".user-item__name")
        playing_element = card.select_one(".user-item__playing")

        if not name_element or not playing_element:
            continue

        title = name_element.get_text(" ", strip=True)
        playing = playing_element.get_text(" ", strip=True)

        if not is_cricket_event(title, playing):
            continue

        # Match card-এর ভেতরের relative URL নেবে।
        link_element = card.select_one("a[href]")
        if not link_element:
            continue

        page_url = urljoin(BASE_URL, link_element["href"])

        if urlparse(page_url).netloc != urlparse(BASE_URL).netloc:
            continue

        if page_url in seen:
            continue

        seen.add(page_url)

        results.append({
            "title": html.unescape(title).upper(),
            "playing": playing,
            "page": page_url,
        })

    return results


def extract_m3u8(page_url):
    try:
        response = requests.get(
            page_url,
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        page_html = response.text

        # d1 + d2 + d3 stream pattern
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
        else:
            # Direct m3u8 URL
            match = re.search(
                r"""https?://[^\s"'<>]+\.m3u8(?:\?[^\s"'<>]*)?""",
                page_html,
                re.IGNORECASE,
            )

            if not match:
                print(f"NO STREAM: {page_url}")
                return None

            stream_url = html.unescape(match.group(0))

        return stream_url

    except requests.RequestException as error:
        print(f"PAGE ERROR: {page_url} - {error}")
        return None


def build_m3u(items, out_file="playlist.m3u"):
    unique_items = []
    seen_streams = set()

    for item in items:
        stream_url = item["url"]

        if stream_url in seen_streams:
            continue

        seen_streams.add(stream_url)
        unique_items.append(item)

    with open(out_file, "w", encoding="utf-8") as file:
        file.write("#EXTM3U\n")

        for item in unique_items:
            title = item["title"]

            # Prevent quotes from breaking M3U attributes.
            safe_title = title.replace('"', "'")

            file.write(
                f'#EXTINF:-1 tvg-name="{safe_title}" '
                f'tvg-logo="{CRICKET_LOGO}" '
                f'group-title="TOP EVENTS",{safe_title}\n'
            )

            file.write(
                f"#EXTVLCOPT:http-referrer={REFERER}\n"
            )
            file.write(
                f"#EXTVLCOPT:http-origin={ORIGIN}\n"
            )
            file.write(
                f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n"
            )

            file.write(
                "#EXTHTTP:"
                '{"referer":"' + REFERER + '",'
                '"origin":"' + ORIGIN + '",'
                '"user-agent":"' + USER_AGENT + '"}\n'
            )

            file.write(item["url"] + "\n\n")

    print(f"\nPlaylist saved: {out_file}")
    print(f"Total cricket streams: {len(unique_items)}")


def main():
    try:
        matches = get_cricket_links()
        print(f"Cricket matches found: {len(matches)}")

        playlist_items = []

        for match in matches:
            print(f"Checking: {match['title']}")

            stream_url = extract_m3u8(match["page"])

            if stream_url:
                playlist_items.append({
                    "title": match["title"],
                    "url": stream_url,
                })
                print(f"STREAM FOUND: {match['title']}")
            else:
                print(f"STREAM NOT FOUND: {match['title']}")

        build_m3u(playlist_items)

    except requests.RequestException as error:
        print(f"Website error: {error}")


if __name__ == "__main__":
    main()
