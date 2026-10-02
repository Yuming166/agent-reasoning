"""FxEmbed zero-cost pilot: 15 confirmed accounts, paged statuses + following.

Records: success rate, earliest reachable tweet date, pagination depth,
missing ratio vs profile counts. Raw pages archived.
"""
import json, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import requests

BASE = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
RAW = BASE/'artifacts/ens_x_crosswalk/fx_pilot_raw'
SAMPLE = BASE/'artifacts/ens_x_crosswalk/verification_sample_v2_filled.csv'
OUT = BASE/'artifacts/ens_x_crosswalk/fx_pilot_metrics.csv'
PROXIES = {"http": "http://10.63.0.72:7890", "https": "http://10.63.0.72:7890"}
UA = {"User-Agent": "exgraph-research/0.1 (academic feasibility pilot)"}
API = "https://api.fxtwitter.com/2/profile/{h}/{kind}"
STATUS_PAGES, FOLLOW_PAGES = 8, 3

def get(h, kind, cursor=None):
    p = {"cursor": cursor} if cursor else {}
    r = requests.get(API.format(h=h, kind=kind), params=p, headers=UA, proxies=PROXIES, timeout=30)
    return r.status_code, r.json()

def paged(h, kind, max_pages, save_dir):
    save_dir.mkdir(parents=True, exist_ok=True)
    pages, cursor, allres, err = 0, None, [], None
    while pages < max_pages:
        try:
            code, d = get(h, kind, cursor)
        except Exception as e:
            err = "exc:"+repr(e); break
        (save_dir/f"p{pages}.json").write_text(json.dumps(d, ensure_ascii=False))
        if code != 200 or d.get("code") != 200:
            err = f"http_{code}/api_{d.get('code')}"; break
        res = d.get("results") or []
        allres.extend(res); pages += 1
        cursor = (d.get("cursor") or {}).get("bottom")
        if not res or not cursor: break
        time.sleep(0.6)
    return pages, allres, err, bool(cursor)

def main():
    df = pd.read_csv(SAMPLE)
    conf = df[df.verification_status=='account_confirms'][['pair_id','handle','x_user_id','status']].drop_duplicates('handle')
    print(f"{len(conf)} confirmed unique handles", flush=True)
    rows = []
    for _, r in conf.iterrows():
        h = r['handle']
        prof_code, prof = get(h, "")
        tw_count = (prof.get('user') or {}).get('tweets') if prof.get('user') else None
        fng_count = (prof.get('user') or {}).get('following') if prof.get('user') else None
        time.sleep(0.6)
        sp, tweets, serr, smore = paged(h, "statuses", STATUS_PAGES, RAW/h/"statuses")
        dates = []
        for t in tweets:
            ts = t.get('created_timestamp')
            if ts: dates.append(datetime.fromtimestamp(int(ts), tz=timezone.utc))
        fp, folls, ferr, fmore = paged(h, "following", FOLLOW_PAGES, RAW/h/"following")
        rows.append({
            "pair_id": r['pair_id'], "handle": h, "link_status": r['status'],
            "profile_ok": prof_code==200, "profile_tweet_count": tw_count, "profile_following_count": fng_count,
            "status_pages": sp, "statuses_fetched": len(tweets), "status_err": serr,
            "status_more_pages": smore,
            "earliest_tweet": min(dates).isoformat() if dates else None,
            "latest_tweet": max(dates).isoformat() if dates else None,
            "n_retweets": sum(1 for t in tweets if t.get('reposted_by')),
            "following_pages": fp, "following_fetched": len(folls), "following_err": ferr,
            "following_more_pages": fmore,
        })
        print(f"{h}: statuses={len(tweets)}/{tw_count} earliest={rows[-1]['earliest_tweet']} more={smore} | following={len(folls)}/{fng_count} err={serr or ferr or '-'}", flush=True)
        time.sleep(0.6)
    m = pd.DataFrame(rows)
    m.to_csv(OUT, index=False)
    print("\n== summary ==")
    print("accounts with statuses>0:", (m.statuses_fetched>0).sum(), "/", len(m))
    print("accounts with following>0:", (m.following_fetched>0).sum(), "/", len(m))
    print(m[['handle','statuses_fetched','profile_tweet_count','earliest_tweet','status_more_pages','following_fetched','profile_following_count','following_more_pages']].to_string(index=False))
    print("saved ->", OUT)

if __name__ == "__main__":
    main()
