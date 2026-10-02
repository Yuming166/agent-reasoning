#!/usr/bin/env python3
"""Synthetic motif-injection benchmark for label-free structural sensitivity.

This is not a criminal-simulation benchmark. It injects controlled directed motifs
into real EX-Graph daily edge backgrounds and asks whether simple scores recover the
injected nodes/groups under camouflage. It never uses wash labels.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EDGE_PATH = ROOT / "research/community_temporal/results/data/edges_day_20220303_20220901.csv"
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MOTIFS = ["cycle", "fan_in", "fan_out", "rapid_forwarding", "split_merge", "reciprocal"]
STAGES = ["S1_obvious", "S2_noise", "S3_camouflage", "S4_high_camouflage"]
SEEDS = list(range(10))
N_GROUPS = 8


def motif_edges(kind: str, nodes: list[int]) -> list[tuple[int, int]]:
    if kind == "cycle":
        return [(nodes[i], nodes[(i + 1) % len(nodes)]) for i in range(len(nodes))]
    if kind == "fan_in":
        return [(u, nodes[-1]) for u in nodes[:-1]]
    if kind == "fan_out":
        return [(nodes[0], v) for v in nodes[1:]]
    if kind == "rapid_forwarding":
        return list(zip(nodes[:-1], nodes[1:]))
    if kind == "split_merge":
        return [(nodes[0], u) for u in nodes[1:-1]] + [(u, nodes[-1]) for u in nodes[1:-1]]
    if kind == "reciprocal":
        return [(nodes[i], nodes[j]) for i, j in [(0, 1), (1, 0), (1, 2), (2, 1)]]
    raise ValueError(kind)


def inject_background(df: pd.DataFrame, seed: int, stage: str, rng: np.random.Generator):
    # Keep a real daily background but avoid reusing the same day deterministically.
    days = sorted(df.day.unique())
    day = days[seed % len(days)]
    bg = df[df.day == day][["u", "v", "weight"]].copy()
    # Sample the background to keep the benchmark bounded and reproducible.
    if len(bg) > 2500:
        bg = bg.sample(2500, random_state=seed)
    edges = [(int(r.u), int(r.v), int(r.weight)) for r in bg.itertuples(index=False)]
    groups: dict[str, set[int]] = {}
    next_id = 1_000_000 + seed * 100_000
    bg_nodes = np.unique(np.r_[bg.u.to_numpy(), bg.v.to_numpy()]).astype(int)
    for gi in range(N_GROUPS):
        kind = MOTIFS[gi % len(MOTIFS)]
        n = 4 if kind not in {"fan_in", "fan_out", "split_merge"} else 6
        nodes = list(range(next_id, next_id + n))
        next_id += 100
        groups[f"g{gi:02d}_{kind}"] = set(nodes)
        for u, v in motif_edges(kind, nodes):
            w = int(rng.integers(1, 4))
            edges.append((u, v, w))
        # Camouflage increases unrelated-looking edges and removes/perturbs some motif signal.
        if stage in {"S2_noise", "S3_camouflage", "S4_high_camouflage"}:
            n_noise = {"S2_noise": 2, "S3_camouflage": 4, "S4_high_camouflage": 8}[stage]
            for _ in range(n_noise):
                u, v = rng.choice(nodes, 2, replace=False)
                edges.append((int(u), int(v), int(rng.integers(1, 3))))
        if stage in {"S3_camouflage", "S4_high_camouflage"}:
            n_external = {"S3_camouflage": 2, "S4_high_camouflage": 6}[stage]
            for _ in range(n_external):
                u = int(rng.choice(nodes))
                v = int(rng.choice(bg_nodes))
                edges.append((u, v, int(rng.integers(1, 3))))
        if stage == "S4_high_camouflage":
            # Remove one canonical edge and add amount/weight noise to weaken exact motifs.
            canonical = motif_edges(kind, nodes)
            if canonical:
                drop = canonical[int(rng.integers(0, len(canonical)))]
                edges = [e for e in edges if not (e[0] == drop[0] and e[1] == drop[1])]
            for _ in range(3):
                u, v = rng.choice(nodes, 2, replace=False)
                edges.append((int(u), int(v), int(rng.integers(1, 8))))
    return edges, groups, str(day)


def graph_scores(edges: list[tuple[int, int, int]]) -> tuple[nx.DiGraph, dict[str, dict[int, float]]]:
    g = nx.DiGraph()
    for u, v, w in edges:
        if u == v:
            continue
        g.add_edge(u, v, weight=g.get_edge_data(u, v, {}).get("weight", 0) + w)
    nodes = list(g.nodes)
    total = {}
    reciprocity = {}
    triangles = {}
    for u in nodes:
        out_w = sum(g[u][v]["weight"] for v in g.successors(u))
        in_w = sum(g[v][u]["weight"] for v in g.predecessors(u))
        total[u] = float(out_w + in_w)
        reciprocity[u] = float(sum(1 for v in g.successors(u) if g.has_edge(v, u)))
        tri = 0
        out_n = set(g.successors(u))
        in_n = set(g.predecessors(u))
        for v in out_n:
            tri += len(out_n.intersection(set(g.successors(v))))
        for v in in_n:
            tri += len(in_n.intersection(set(g.predecessors(v))))
        triangles[u] = float(tri)
    # A deliberately simple structural composite; no external labels are used.
    structural = {
        u: math.log1p(total[u]) + 1.5 * reciprocity[u] + 1.5 * math.log1p(triangles[u])
        for u in nodes
    }
    return g, {"volume": total, "reciprocity": reciprocity, "triangles": triangles, "structural": structural}


def top_nodes(score: dict[int, float], k: int) -> set[int]:
    return {n for n, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:k]}


def ego_candidates(g: nx.DiGraph, node_score: dict[int, float], limit: int = 200):
    seeds = sorted(node_score, key=lambda n: (-node_score[n], n))[:limit]
    candidates = []
    seen: set[frozenset[int]] = set()
    for u in seeds:
        nodes = set([u]) | set(g.predecessors(u)) | set(g.successors(u))
        key = frozenset(nodes)
        if len(nodes) < 3 or key in seen:
            continue
        seen.add(key)
        sub = g.subgraph(nodes)
        possible = max(1, len(nodes) * (len(nodes) - 1))
        density = sub.number_of_edges() / possible
        internal_weight = sum(d.get("weight", 1) for _, _, d in sub.edges(data=True))
        score = density * math.log1p(internal_weight) * math.log1p(len(nodes))
        candidates.append((score, nodes))
    return sorted(candidates, key=lambda x: (-x[0], tuple(sorted(x[1]))))


def group_recovery(candidates, groups: dict[str, set[int]], top_k: int) -> tuple[float, float]:
    selected = candidates[:top_k]
    hits = 0
    best_ious = []
    for target in groups.values():
        best = 0.0
        for _, cand in selected:
            inter = len(target & cand)
            union = len(target | cand)
            best = max(best, inter / union if union else 0.0)
        best_ious.append(best)
        hits += best >= 0.5
    return hits / len(groups), float(np.mean(best_ious))


def main() -> None:
    df = pd.read_csv(EDGE_PATH)
    data_sha = hashlib.sha256(EDGE_PATH.read_bytes()).hexdigest()
    rows = []
    for seed in SEEDS:
        for stage in STAGES:
            rng = np.random.default_rng(seed * 100 + STAGES.index(stage))
            edges, groups, day = inject_background(df, seed, stage, rng)
            g, scores = graph_scores(edges)
            injected_nodes = set().union(*groups.values())
            for score_name, score in scores.items():
                for k in (25, 50, 100, 200):
                    recovered = len(top_nodes(score, k) & injected_nodes) / len(injected_nodes)
                    rows.append({
                        "seed": seed, "stage": stage, "background_day": day,
                        "motif_mix": "six_known_motifs", "score": score_name,
                        "unit": "node", "k": k, "recall": recovered,
                        "n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges(),
                    })
            for score_name, score in scores.items():
                cand = ego_candidates(g, score)
                for k in (10, 25, 50):
                    hit, mean_iou = group_recovery(cand, groups, k)
                    rows.append({
                        "seed": seed, "stage": stage, "background_day": day,
                        "motif_mix": "six_known_motifs", "score": score_name,
                        "unit": "group_ego", "k": k, "group_hit_rate": hit,
                        "mean_best_iou": mean_iou,
                        "n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges(),
                    })
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "synthetic_motif_injection_results.csv", index=False)
    summary = {
        "experiment_id": "OW-004",
        "edge_background": str(EDGE_PATH),
        "edge_background_sha256": data_sha,
        "label_access": "none",
        "seeds": SEEDS,
        "stages": STAGES,
        "motifs": MOTIFS,
        "n_groups": N_GROUPS,
        "notes": "Structural sensitivity only; not realistic criminal simulation.",
        "rows": len(out),
    }
    (OUT_DIR / "synthetic_motif_injection_manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(out.groupby(["stage", "score", "unit", "k"], dropna=False).mean(numeric_only=True).round(4).to_string())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
