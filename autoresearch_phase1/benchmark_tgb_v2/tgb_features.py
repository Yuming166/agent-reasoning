#!/usr/bin/env python3
"""Leak-free prefix-based temporal graph features for tgbl-coin-v2 (torch/numpy only).

Builds global sorted structures over ALL edges once, then answers per-query
(u, v, t) features with vectorized np.searchsorted. Features are computed
strictly from events with timestamp < t (state "before" the query), so no
future leakage. Because TGB splits are temporally contiguous, querying against
the full edge list is exactly equivalent to querying against the streaming
history state used by the official protocol (train for val queries; train+val
for test queries), up to timestamp-tie edge cases within an eval batch.

Features (23 dims, all log1p-scaled / binarized):
  src: out_total, out_last_gap, out_distinct, out_decay7d, in_total, in_last_gap
  dst: in_total, in_last_gap, in_distinct, in_decay7d, out_total, out_last_gap
  pair(u,v): count, last_gap, has, count_1h, count_1d, count_7d, decay1d
  reverse(v,u): rev_count, rev_last_gap, has_rev
"""
import numpy as np

BIG = 1 << 31   # > max timestamp (1.667e9)
BIG2 = 1 << 32  # for compact pair-idx keying


def _build_node_struct(node_ids, aux_ids, t, N, t_max, tau):
    """Events sorted by (node, t); per-node prefix lookups via composite key."""
    key = node_ids * BIG + t
    order = np.argsort(key, kind="stable")
    skey = key[order]
    st = t[order]
    saux = aux_ids[order]
    # per-node group starts (over full node range; -1 if absent)
    uniq_nodes, first_pos = np.unique(node_ids[order], return_index=True)
    start = np.full(N, -1, dtype=np.int64)
    start[uniq_nodes] = first_pos
    n_nodes = len(uniq_nodes)
    end = np.full(N, -1, dtype=np.int64)
    end[uniq_nodes[:-1]] = first_pos[1:]
    end[uniq_nodes[-1]] = len(node_ids)
    # distinct-aux flags: first (in time order) occurrence of (node, aux)
    code_nat = node_ids * N + aux_ids          # bijection for (node, aux)
    order_nat = np.lexsort((t, aux_ids, node_ids))
    code_nat_sorted = code_nat[order_nat]
    _, nat_starts = np.unique(code_nat_sorted, return_index=True)
    nat_first = np.zeros(len(node_ids), dtype=np.int8)
    nat_first[nat_starts] = 1
    # map nat order -> (node,t) order
    inv_nat = np.empty(len(node_ids), dtype=np.int64)
    inv_nat[order_nat] = np.arange(len(node_ids))
    flag_nt = nat_first[inv_nat[order]]
    cum_new = np.cumsum(flag_nt, dtype=np.int64)
    # decayed activity prefix: per-group cumsum of exp((t'-t_max)/tau)
    exp_t = np.exp((st - t_max) / tau)
    grp_cum = np.empty(len(exp_t), dtype=np.float64)
    for g in uniq_nodes:
        a = start[g]; b = end[g]
        if b - a == 1:
            grp_cum[a] = exp_t[a]
        else:
            grp_cum[a:b] = np.cumsum(exp_t[a:b])
    return {
        "key": skey, "evt_t": st, "evt_aux": saux,
        "start": start, "end": end,
        "cum_new": cum_new, "grp_cum": grp_cum,
        "exp_t": exp_t, "t_max": t_max, "tau": tau,
    }


def _build_pair_struct(s, d, t, N, t_max, tau):
    """Events sorted by (compact_pair_idx, t); per-pair prefix lookups."""
    codes = s * N + d
    uniq_codes = np.unique(codes)
    pair_idx = np.searchsorted(uniq_codes, codes)
    P = len(uniq_codes)
    key = pair_idx * BIG2 + t
    order = np.argsort(key, kind="stable")
    skey = key[order]
    st = t[order]
    sidx = pair_idx[order]
    uniq_idx, first_pos = np.unique(sidx, return_index=True)
    start = np.full(P, -1, dtype=np.int64)
    start[uniq_idx] = first_pos
    end = np.full(P, -1, dtype=np.int64)
    end[uniq_idx[:-1]] = first_pos[1:]
    end[uniq_idx[-1]] = len(s)
    exp_t = np.exp((st - t_max) / tau)
    grp_cum = np.empty(len(exp_t), dtype=np.float64)
    for g in uniq_idx:
        a = start[g]; b = end[g]
        if b - a == 1:
            grp_cum[a] = exp_t[a]
        else:
            grp_cum[a:b] = np.cumsum(exp_t[a:b])
    return {
        "uniq_codes": uniq_codes, "key": skey, "evt_t": st,
        "start": start, "end": end, "grp_cum": grp_cum, "exp_t": exp_t,
        "t_max": t_max, "tau": tau,
    }


class PrefixGraphFeatures:
    def __init__(self, s, d, t, tau_node=7 * 86400, tau_pair=86400):
        s = np.asarray(s, dtype=np.int64)
        d = np.asarray(d, dtype=np.int64)
        t = np.asarray(t, dtype=np.int64)
        self.N = int(max(s.max(), d.max())) + 1
        self.t_max = int(t.max())
        self.out = _build_node_struct(s, d, t, self.N, self.t_max, tau_node)
        self.inn = _build_node_struct(d, s, t, self.N, self.t_max, tau_node)
        self.pair = _build_pair_struct(s, d, t, self.N, self.t_max, tau_pair)
        self.rev = _build_pair_struct(d, s, t, self.N, self.t_max, tau_pair)

    # ---------------- node lookups ----------------
    def _node_stats(self, st, node, t, want_distinct=True, want_decay=True):
        key = node * BIG + t
        gpos = np.searchsorted(st["key"], key, side="left")
        valid = st["start"][node] >= 0
        stt = st["start"][node]
        cnt = np.where(valid, gpos - stt, 0)
        cnt = np.maximum(cnt, 0)
        has = cnt > 0
        # last time before t
        last_t = np.full(len(node), -1, dtype=np.int64)
        gp1 = gpos - 1
        mask = has
        last_t[mask] = st["evt_t"][gp1[mask]]
        gap = np.where(mask, t - last_t, 0)
        gap = np.maximum(gap, 0)
        out = {"cnt": cnt, "gap": gap, "last_t": last_t}
        if want_distinct:
            stm1 = np.where(stt > 0, stt - 1, 0)
            cum_at = np.where(has, st["cum_new"][gp1], 0)
            cum_start = np.where(stt > 0, st["cum_new"][stm1], 0)
            distinct = np.where(has, cum_at - cum_start, 0)
            distinct = np.maximum(distinct, 0)
            out["distinct"] = distinct
        if want_decay:
            cum_at = np.where(has, st["grp_cum"][gp1], 0.0)
            dec = np.maximum(cum_at, 0.0) * np.exp((st["t_max"] - t) / st["tau"])
            out["decay"] = dec
        return out

    # ---------------- pair lookups ----------------
    def _pair_stats(self, ps, u, v, t):
        codes = u * self.N + v
        idx = np.searchsorted(ps["uniq_codes"], codes, side="left")
        ok = idx < len(ps["uniq_codes"])
        safe = np.minimum(idx, len(ps["uniq_codes"]) - 1)
        ok &= ps["uniq_codes"][safe] == codes
        idx_safe = np.where(ok, idx, 0)
        key = idx_safe * BIG2 + t
        gpos = np.searchsorted(ps["key"], key, side="left")
        stt = np.where(ok, ps["start"][idx_safe], 0)
        cnt = np.where(ok, gpos - stt, 0)
        cnt = np.maximum(cnt, 0)
        has = ok & (cnt > 0)
        last_t = np.full(len(u), -1, dtype=np.int64)
        gp1 = gpos - 1
        last_t[has] = ps["evt_t"][gp1[has]]
        gap = np.where(has, t - last_t, 0)
        gap = np.maximum(gap, 0)
        out = {"cnt": cnt, "gap": gap, "has": has.astype(np.float32), "last_t": last_t}
        # window counts
        for wname, wsec in (("w1h", 3600), ("w1d", 86400), ("w7d", 604800)):
            keyw = idx_safe * BIG2 + (t - wsec)
            gw = np.searchsorted(ps["key"], keyw, side="left")
            cntw = np.where(ok, gw - stt, 0)
            cntw = np.maximum(cntw, 0)
            out[wname] = np.maximum(cnt - cntw, 0)
        # decayed pair
        cum_at = np.where(has, ps["grp_cum"][gp1], 0.0)
        dec = np.maximum(cum_at, 0.0) * np.exp((ps["t_max"] - t) / ps["tau"])
        out["decay"] = dec
        return out

    def features(self, u, v, t):
        u = np.asarray(u, dtype=np.int64)
        v = np.asarray(v, dtype=np.int64)
        t = np.asarray(t, dtype=np.int64)
        o = self._node_stats(self.out, u, t)          # src out
        i = self._node_stats(self.inn, v, t)          # dst in
        so = self._node_stats(self.inn, u, t)         # src in
        do = self._node_stats(self.out, v, t)         # dst out
        p = self._pair_stats(self.pair, u, v, t)
        r = self._pair_stats(self.rev, u, v, t)
        F = np.column_stack([
            np.log1p(o["cnt"]), np.log1p(o["gap"]), np.log1p(o["distinct"]),
            np.log1p(o["decay"]), np.log1p(so["cnt"]), np.log1p(so["gap"]),
            np.log1p(i["cnt"]), np.log1p(i["gap"]), np.log1p(i["distinct"]),
            np.log1p(i["decay"]), np.log1p(do["cnt"]), np.log1p(do["gap"]),
            np.log1p(p["cnt"]), np.log1p(p["gap"]), p["has"],
            np.log1p(p["w1h"]), np.log1p(p["w1d"]), np.log1p(p["w7d"]),
            np.log1p(p["decay"]),
            np.log1p(p["cnt"] / (1.0 + o["cnt"])),
            np.log1p(r["cnt"]), np.log1p(r["gap"]), r["has"],
        ])
        return F.astype(np.float32)


FEATURE_NAMES = [
    "src_out_total", "src_out_last_gap", "src_out_distinct", "src_out_decay7d",
    "src_in_total", "src_in_last_gap",
    "dst_in_total", "dst_in_last_gap", "dst_in_distinct", "dst_in_decay7d",
    "dst_out_total", "dst_out_last_gap",
    "pair_count", "pair_last_gap", "has_pair",
    "pair_1h", "pair_1d", "pair_7d", "pair_decay1d", "pair_count_ratio",
    "rev_count", "rev_last_gap", "has_rev",
]
