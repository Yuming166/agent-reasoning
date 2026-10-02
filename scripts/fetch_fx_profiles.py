"""Fetch X profile bio/id via api.fxtwitter.com (public mirror, no key)."""
import json, time
from pathlib import Path
import pandas as pd
import requests

BASE = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RAW = BASE/'artifacts/ens_x_crosswalk/fx_raw'
SAMPLE = BASE/'artifacts/ens_x_crosswalk/verification_sample_v2.csv'
OUT = BASE/'artifacts/ens_x_crosswalk/fx_profiles_parsed.jsonl'
PROXIES = {"http": "http://10.63.0.72:7890", "https": "http://10.63.0.72:7890"}
UA = {"User-Agent": "exgraph-research/0.1 (academic; no-auth)"}

def fetch(handle):
    p = RAW/(handle.lower()+'.json')
    if p.exists():
        return json.loads(p.read_text())
    try:
        r = requests.get(f"https://api.fxtwitter.com/{handle}", headers=UA, proxies=PROXIES, timeout=30, allow_redirects=False)
        if r.status_code == 200:
            rec = {"handle": handle, "http_status": 200, "data": r.json()}
        else:
            rec = {"handle": handle, "http_status": r.status_code, "error": "http_"+str(r.status_code)}
    except Exception as e:
        rec = {"handle": handle, "http_status": None, "error": "exc:"+repr(e)}
    p.write_text(json.dumps(rec, ensure_ascii=False))
    return rec

def parse(rec):
    out = {"handle": rec["handle"], "http_status": rec.get("http_status")}
    if rec.get("error"):
        out["error"] = rec["error"]; return out
    u = (rec.get("data") or {}).get("user")
    if not u:
        out["error"] = "no_user"; return out
    out.update({"fx_user_id": u.get("id"), "screen_name": u.get("screen_name"),
                "x_name": u.get("name"), "description": u.get("description"),
                "followers": u.get("followers"), "tweets_count": u.get("tweets"),
                "profile_url": u.get("url"),
                "banner_website": (u.get("website") or {}).get("url") if isinstance(u.get("website"), dict) else u.get("website")})
    return out

def main():
    df = pd.read_csv(SAMPLE)
    results = []
    for i, h in enumerate(df['handle'].tolist()):
        rec = fetch(h)
        results.append(parse(rec))
        print(f"[{i+1}/{len(df)}] {h}: {results[-1].get('error') or 'ok'}", flush=True)
        time.sleep(1.0)
    with open(OUT, 'w') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False)+"\n")
    print("done")

if __name__ == "__main__":
    main()
