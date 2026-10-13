
#!/usr/bin/python3

import os
import re
import sys
import html
import requests


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def log(message):
    print(message, file=sys.stderr)


def grab(url):
    try:
        response = requests.get(
            url,
            timeout=15,
            headers=HEADERS
        )
        response.raise_for_status()

        page = html.unescape(response.text)

        # Handle escaped URLs in JSON/JavaScript
        page = page.replace(r"\/", "/")
        page = page.replace(r"\u0026", "&")
        page = page.replace(r"\u003d", "=")
        page = page.replace(r"\u003f", "?")

        pattern = (
            r'https?://[^\s"\'<>\\]+?\.m3u8'
            r'(?:\?[^\s"\'<>\\]*)?'
        )

        matches = re.findall(
            pattern,
            page,
            flags=re.IGNORECASE
        )

        if not matches:
            log(f"# M3U8 not found: {url}")
            return None

        return matches[0].rstrip(".,;)]}")

    except requests.RequestException as exc:
        log(f"# Request failed: {url} - {exc}")
        return None


def main():
    input_file = "youtubeLink.txt"

    if not os.path.isfile(input_file):
        log(f"# Input file not found: {input_file}")
        sys.exit(1)

    # Write playlist to stdout so GitHub Actions can
    # save it using: python main.py > playlist.m3u
    print("#EXTM3U")

    with open(input_file, encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()

            if not line or line.startswith("##"):
                continue

            if line.lower().startswith(("https://", "http://")):
                stream_url = grab(line)

                if stream_url:
                    # A URL-only entry gets a default name.
                    print('#EXTINF:-1,Live Channel')
                    print(stream_url)

                continue

            # Split only on the first hyphen.
            if "-" not in line:
                log(f"# Skipping invalid entry: {line}")
                continue

            ch_name, grp_title = line.split("-", 1)

            ch_name = ch_name.strip()
            grp_title = grp_title.strip().title()

            if not ch_name or not grp_title:
                log(f"# Skipping incomplete entry: {line}")
                continue

            print(
                f'#EXTINF:-1 group-title="{grp_title}",{ch_name}'
            )


if __name__ == "__main__":
    main()

    if os.path.isfile("temp.txt"):
        os.remove("temp.txt")

    # Remove generated watch files, if any.
    for filename in os.listdir("."):
        if filename.startswith("watch") and os.path.isfile(filename):
            os.remove(filename)
