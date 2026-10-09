import requests
import re
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup

BASE_URL = "http://www.fawanews.sc/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
REFERER = "http://www.fawanews.sc/"
ORIGIN = "http://www.fawanews.sc/"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "Origin": ORIGIN,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def get_index_links():
    r = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.select("a[href$='.html']"):
        href = a.get("href")
        # sudhu match page gulo, contact/privacy bad
        if href in ["contact.html","privacy_policy.html","index.html"]: 
            continue
        if len(href) < 5: 
            continue
        full = urljoin(BASE_URL, href)
        links.append(full)
    # duplicate remove
    links = list(dict.fromkeys(links))
    return links

def extract_m3u8(page_url):
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text

        # tomar example pattern
        # var d1 = "http://193.47.62.44/hls/";
        # var d2 = "seeeX";
        # var d3 = ".m3u8";
        d1 = re.search(r'var\s+d1\s*=\s*"([^"]+)"', html)
        d2 = re.search(r'var\s+d2\s*=\s*"([^"]+)"', html)
        d3 = re.search(r'var\s+d3\s*=\s*"([^"]+)"', html)

        if not (d1 and d2 and d3):
            # kichu page e direct VVVV te thake
            m = re.search(r'https?://[^\s"\']+\.m3u8', html)
            if m:
                return m.group(0)
            return None

        m3u8 = d1.group(1) + d2.group(1) + d3.group(1)
        
        # Title ber kora
        title_match = re.search(r'<title>FawaNews - (.*?) - Your Home', html)
        title = title_match.group(1).strip() if title_match else page_url.split("/")[-1].replace(".html","")

        return {"title": title, "url": m3u8, "page": page_url}
    except Exception as e:
        print(f"Error {page_url}: {e}")
        return None

def build_m3u(items, out_file="playlist.m3u"):
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for it in items:
            if not it: continue
            f.write(f'#EXTINF:-1 tvg-name="{it["title"]}" group-title="FawaNews",{it["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER}\n')
            f.write(f'#EXTVLCOPT:http-origin={ORIGIN}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            # OTT / TiviMate er jonno extra header
            f.write(f'#EXTHTTP:{{"referer":"{REFERER}","origin":"{ORIGIN}","user-agent":"{USER_AGENT}"}}\n')
            f.write(f"{it['url']}\n\n")
    print(f"Saved {out_file} - {len(items)} channels")

if __name__ == "__main__":
    links = get_index_links()
    print(f"Found {len(links)} match pages")
    results = []
    for link in links:
        data = extract_m3u8(link)
        if data:
            print(f"✓ {data['title']} => {data['url']}")
            results.append(data)

    build_m3u(results)
