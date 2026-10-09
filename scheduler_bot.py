import requests, re, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import subprocess

BASE_URL = "http://www.fawanews.sc/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
REFERER = "http://www.fawanews.sc/"
ORIGIN = "http://www.fawanews.sc/"
DEFAULT_LOGO = "https://i.imgur.com/8Km9tLL.png"
GMT_PLUS_1 = timezone(timedelta(hours=1))

HEADERS = {"User-Agent": USER_AGENT, "Referer": REFERER}

def get_schedule():
    r = requests.get(BASE_URL, headers=HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    schedule = []
    today = datetime.now(GMT_PLUS_1).date()
    for item in soup.select(".user-item"):
        name = item.select_one(".user-item__name")
        playing = item.select_one(".user-item__playing")
        link = item.select_one("a[href$='.html']")
        if not name or not playing or not link: continue
        t = re.search(r'(\d{1,2}:\d{2})', playing.get_text())
        if not t: continue
        h, m = map(int, t.group(1).split(":"))
        start = datetime.combine(today, datetime.min.time(), tzinfo=GMT_PLUS_1).replace(hour=h, minute=m)
        schedule.append({"title": name.get_text(strip=True), "url": urljoin(BASE_URL, link['href']), "start": start, "league": playing.get_text(strip=True)})

    # time onujayi sort
    return sorted(schedule, key=lambda x: x["start"])

def get_m3u8(page_url):
    try:
        html = requests.get(page_url, headers=HEADERS, timeout=15).text
        d1 = re.search(r'var\s+d1\s*=\s*"([^"]+)"', html)
        d2 = re.search(r'var\s+d2\s*=\s*"([^"]+)"', html)
        d3 = re.search(r'var\s+d3\s*=\s*"([^"]+)"', html)
        if d1 and d2 and d3:
            return d1.group(1)+d2.group(1)+d3.group(1)
        m = re.search(r'https?://[^\s"\']+\.m3u8', html)
        return m.group(0) if m else None
    except: return None

def update_playlist_for_match(match):
    print(f"\n[RUNNING] {match['title']} - Start: {match['start']} - ekhon 2 min age playlist banacchi...")
    m3u8 = get_m3u8(match["url"])
    if not m3u8:
        print("m3u8 not ready yet, 30s por abar try")
        time.sleep(30)
        m3u8 = get_m3u8(match["url"])

    if m3u8:
        # playlist e append koro
        with open("playlist.m3u", "a", encoding="utf-8") as f:
            # prothom bar hole header
            if f.tell() == 0:
                pass
        # full rebuild
        existing = []
        if os.path.exists("playlist.m3u"):
            with open("playlist.m3u") as f:
                content = f.read()
                # simple append er jonno amra notun kore banabo na, ekhane sudhu add korchi
                pass

        with open("playlist.m3u", "a", encoding="utf-8") as f:
            if f.tell() == 0:
                f.write("#EXTM3U\n")
            f.write(f'#EXTINF:-1 tvg-name="{match["title"]}" tvg-logo="{DEFAULT_LOGO}" group-title="TOP EVENTS",{match["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER}\n#EXTVLCOPT:http-origin={ORIGIN}\n#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{m3u8}\n\n')

        print(f"Added: {m3u8}")
        # git push
        subprocess.run(["git", "config", "--local", "user.email", "bot@github.com"])
        subprocess.run(["git", "config", "--local", "user.name", "fawa-bot"])
        subprocess.run(["git", "add", "playlist.m3u"])
        subprocess.run(["git", "commit", "-m", f"Add {match['title']} 2min before"])
        subprocess.run(["git", "push"])

if __name__ == "__main__":
    import os
    # start e playlist clear
    open("playlist.m3u","w").write("#EXTM3U\n")

    while True:
        schedule = get_schedule()
        now = datetime.now(GMT_PLUS_1)
        print(f"\n--- Checking schedule at {now} --- Total {len(schedule)} matches")

        upcoming = [s for s in schedule if s["start"] > now]
        if not upcoming:
            print("Ajker ar kono match nei. 1 ghonta sleep.")
            time.sleep(3600)
            continue

        next_match = upcoming[0]
        run_at = next_match["start"] - timedelta(minutes=2)
        seconds_to_wait = (run_at - now).total_seconds()

        print(f"Next match: {next_match['title']} at {next_match['start']} -> Bot run at {run_at}")

        if seconds_to_wait > 0:
            print(f"Sleeping {int(seconds_to_wait)} sec ({int(seconds_to_wait/60)} min) porjonto...")
            time.sleep(seconds_to_wait)

        # 2 min age chole eseche, ekhon playlist banao
        update_playlist_for_match(next_match)
        time.sleep(60) # 1 min wait kore porer match er jonno loop
