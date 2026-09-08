#!/usr/bin/env python3
"""Next-counterparty candidate scoring baselines (local, frozen August).

global_hist   : rank candidate v by historical incoming volume (Mar-Jul)
personal_freq : u's own prior u->v counts
personal_rec  : frequency x exponential recency (90d half-life)
Repeat events rank among the wallet's prior neighbors; new events among
non-neighbors by global popularity. Metrics: MRR, Recall@{1,5,10}.
"""
from __future__ import annotations
import glob, json, os, bisect
import numpy as np
import pandas as pd

NC = "/tmp/nc"; HL_DAYS = 90.0


def load(kind):
    return pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{NC}/{kind}_*.csv"))],
                     ignore_index=True)


def metrics(rank):
    rank = np.asarray(rank)
    rank=np.asarray(rank, dtype=float); rank=np.where(rank<=0, np.inf, rank)
    return {"n": int(len(rank)), "MRR": float((1.0/rank).mean()),
            "Recall@1": float((rank == 1).mean()),
            "Recall@5": float((rank <= 5).mean()),
            "Recall@10": float((rank <= 10).mean())}


def main():
    ev = load("events"); ed = load("edges"); pop = load("pop")
    ev["month"] = pd.to_datetime(ev["month"]).dt.date.astype(str)
    aug = ev[ev.month == "2022-08-01"].reset_index(drop=True)

    pop = pop.sort_values("hist_cnt", ascending=False).reset_index(drop=True)
    gpos = {v: i for i, v in enumerate(pop["v"].to_numpy())}  # 0-based global pos

    # ---- personal ranks: build per-user sorted lists -------------------------
    ed["w"] = np.exp(-np.log(2) * ed["days_since_last"].clip(lower=0)/HL_DAYS)
    ed["recency_score"] = ed["cnt"]*ed["w"]
    freq_map, rec_map, neigh = {}, {}, {}
    for u, g in ed.groupby("u", sort=False):
        gf = g.sort_values("cnt", ascending=False)
        gr = g.sort_values("recency_score", ascending=False)
        freq_map[u] = {v: i+1 for i, v in enumerate(gf["v"].to_numpy())}
        rec_map[u] = {v: i+1 for i, v in enumerate(gr["v"].to_numpy())}
        neigh[u] = set(g["v"].to_numpy())

    U, V, T = aug["u"].to_numpy(), aug["v"].to_numpy(), aug.cp_type.to_numpy()
    isnew = T == "new"
    grank = np.array([gpos.get(v, len(pop))+1 for v in V])
    fr, rr = [], []
    for u, v in zip(U, V):
        fr.append(freq_map.get(u, {}).get(v, 0))
        rr.append(rec_map.get(u, {}).get(v, 0))
    fr, rr = np.array(fr), np.array(rr)
    rep = ~isnew
    # personal models can only rank counterparties visible in Mar-Jul history
    hist_known = fr > 0
    rep_hist = rep & hist_known
    rep_samemonth = rep & ~hist_known

    # ---- global rank among NON-neighbors only (new events) -------------------
    # sorted neighbor global positions per user
    pos_sets = {u: np.sort([gpos[x] for x in s if x in gpos]) for u, s in neigh.items()}
    newrank = grank.copy()
    gpos_v = np.array([gpos.get(v, -1) for v in V])
    for i in np.where(isnew)[0]:
        ps = pos_sets.get(U[i]); pos = gpos_v[i]
        if ps is None or pos < 0:
            continue
        higher = bisect.bisect_left(ps, pos)  # neighbors ranked above v
        newrank[i] = grank[i]-higher

    out = {
        "n_aug_events": int(len(aug)),
        "n_repeat": int(rep.sum()), "n_new": int(isnew.sum()),
        "global_hist_all": metrics(grank),
        "global_hist_repeat": metrics(grank[rep]),
        "global_hist_new": metrics(grank[isnew]),
        "global_hist_new_candidates_only": metrics(newrank[isnew]),
        "personal_freq_repeat_histknown": metrics(fr[rep_hist]),
        "personal_recency_repeat_histknown": metrics(rr[rep_hist]),
        "repeat_histknown_events": int(rep_hist.sum()),
        "repeat_same_month_only_events": int(rep_samemonth.sum()),
        "personal_coverage_of_repeat": float(rep_hist.sum()/max(rep.sum(),1)),
    }
    os.makedirs("artifacts/nc_v1", exist_ok=True)
    json.dump(out, open("artifacts/nc_v1/candidate_baselines_v1.json", "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
