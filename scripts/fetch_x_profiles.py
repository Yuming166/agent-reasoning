"""Fetch public X profile data via syndication.twitter.com embed endpoint (no API key)."""
import json, re, time
from pathlib import Path
import pandas as pd
import requests

BASE = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RAW = BASE/'artifacts/ens_x_crosswalk/x_profiles_raw'
SAMPLE = BASE/'artifacts/ens_x_crosswalk/verification_sample_v2.csv'
OUT = BASE/'artifacts/ens_x_crosswalk/x_profiles_parsed.jsonl'

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
URL = ("https://syndication.twitter.com/srv/timeline-profile/screen-name/{h}"
       "?dnt=true&embedId=twitter-widget-0&lang=en&frame=false&hideBorder=false"
       "&hideFooter=false&hideHeader=false&hideScrollBar=false&maxWidth=600px"
       "&origin=https%3A%2F%2Fpublish.twitter.com&showHeader=true&showReplies=false"
       "&transparent=false&widgetsVersion=2615f7e52b7e0%3A1702314776716")
PROXIES = {"http": "http://10.63.0.72:7890", "https": "http://10.63.0.72:7890"}
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

def fetch(handle):
    raw_path = RAW/(handle.lower()+'.json')
    if raw_path.exists():
        return json.loads(raw_path.read_text())
    for attempt in range(6):
        r = requests.get(URL.format(h=handle), headers=UA, proxies=PROXIES, timeout=30)
        if r.status_code == 200:
            break
        if r.status_code == 429:
            reset = int(r.headers.get("x-rate-limit-reset", "0") or 0)
            wait = max(reset - int(time.time()), 15) + 5
            print(f"    429; sleeping {wait}s until reset", flush=True)
            time.sleep(wait)
            continue
        rec = {"handle": handle, "http_status": r.status_code, "error": "http_"+str(r.status_code)}
        raw_path.write_text(json.dumps(rec))
        return rec
    else:
        rec = {"handle": handle, "http_status": 429, "error": "http_429_exhausted"}
        raw_path.write_text(json.dumps(rec))
        return rec
    m = NEXT_RE.search(r.text)
    if not m:
        rec = {"handle": handle, "http_status": 200, "error": "no_next_data"}
        raw_path.write_text(json.dumps(rec))
        return rec
    data = json.loads(m.group(1))
    raw_path.write_text(json.dumps({"handle": handle, "http_status": 200, "data": data}))
    return {"handle": handle, "http_status": 200, "data": data}

def parse(rec):
    out = {"handle": rec["handle"], "http_status": rec.get("http_status")}
    if rec.get("error"):
        out["error"] = rec["error"]
        return out
    try:
        entries = rec["data"]["props"]["pageProps"]["timeline"]["entries"]
    except Exception as e:
        out["error"] = "parse:"+repr(e)
        return out
    user, tweets = None, []
    for e in entries:
        tw = e.get("content", {}).get("tweet")
        if not tw: continue
        u = tw.get("user", {})
        if user is None and u.get("id_str") not in (None, "0", 0):
            user = u
        tweets.append({"id_str": tw.get("id_str"), "created_at": tw.get("created_at"),
                       "full_text": tw.get("full_text"), "permalink": tw.get("permalink")})
    if user is None:
        hp = rec["data"]["props"]["pageProps"].get("headerProps", {})
        out["error"] = "no_user_entries"
        out["header_screen_name"] = hp.get("screenName")
        return out
    out.update({
        "x_user_id": user.get("id_str"),
        "screen_name": user.get("screen_name"),
        "x_name": user.get("name"),
        "description": user.get("description"),
        "protected": user.get("protected"),
        "followers_count": user.get("followers_count"),
        "account_created_at": user.get("created_at"),
        "profile_urls": [u.get("expanded_url") for u in user.get("entities", {}).get("url", {}).get("urls", [])]
                        + [u.get("expanded_url") for u in user.get("entities", {}).get("description", {}).get("urls", [])],
        "tweets": tweets,
    })
    return out

def main():
    df = pd.read_csv(SAMPLE)
    handles = df['handle'].tolist()
    results = []
    for i, h in enumerate(handles):
        try:
            rec = fetch(h)
            results.append(parse(rec))
            st = results[-1].get('error') or results[-1].get('http_status')
            print(f"[{i+1}/{len(handles)}] {h}: {st}", flush=True)
        except Exception as e:
            print(f"[{i+1}/{len(handles)}] {h}: EXC {e!r}", flush=True)
            results.append({"handle": h, "error": "exc:"+repr(e)})
        time.sleep(4)
    with open(OUT, 'w') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False)+"\n")
    print("done ->", OUT)

if __name__ == "__main__":
    main()
