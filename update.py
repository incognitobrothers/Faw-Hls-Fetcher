import cloudscraper
import re
import logging
import sys
import requests

REQUESTS_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
REFERER = "https://executeandship.com/"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

def get_m3u8_from_fid(fid):
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    scraper.headers.update({
        'User-Agent': USER_AGENT,
        'Referer': REFERER
    })

    iframe_url = f"https://executeandship.com/premiumcr.php?player=desktop&live={fid}"
    logging.info(f"Fetching: {iframe_url}")

    try:
        r = scraper.get(iframe_url, timeout=REQUESTS_TIMEOUT)
        r.raise_for_status()
        html = r.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None

    # JS এর ভিতর return ["h","t","t","p"...].join('') এর মতো থাকে
    stream_array_match = re.search(r"return \[(.*?)\]\.join", html, re.DOTALL)
    if not stream_array_match:
        logging.error("stream array পাওয়া যায়নি। Cloudflare challenge বা token expire হতে পারে")
        return None

    char_list_str = stream_array_match.group(1)
    char_list = re.findall(r'"([^"]*)"', char_list_str)
    final_url = "".join(char_list).replace("\\/", "/")

    return final_url

if __name__ == "__main__":
    fid = "ptvpk"  # এখানে তোমার fid বসাও
    stream_url = get_m3u8_from_fid(fid)

    if stream_url:
        logging.info("--- SUCCESS ---")
        print(f"\nFinal Stream URL:\n{stream_url}\n")
        with open("siamscrichd.m3u", "w") as f:
            f.write("#EXTM3U\n")
            f.write(f"#EXTINF:-1,WILLOW HD - {fid}\n")
            f.write(stream_url + "\n")
        logging.info("m3u ফাইল বানানো শেষ: siamscrichd.m3u")
    else:
        logging.error("--- FAILED ---")
        sys.exit(1)
