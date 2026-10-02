#!/usr/bin/env python3
"""Audit the frozen crypto-influencer context before model integration.

This is an offline, deterministic audit.  It does not call an LLM and does not
join social entities to wallets.  The output is intentionally an audit artifact
rather than a predictive result.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/crypto_influencer_v5/dataset_52-person-from-2021-02-05_2023-06-12_21-34-17-266_with_sentiment.csv"
EVENTS = ROOT / "artifacts/motif_hypothesis_eventlevel_20260927/raw_events.jsonl"
OUT = ROOT / "artifacts/influencer_context_audit_20260928"

# Conservative aliases only.  Unknown strings remain visible as normalized_raw
# and are not silently treated as a canonical asset/entity.
ALIASES = {
    "btc": "bitcoin", "xbt": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "avax": "avalanche", "avalanche": "avalanche",
    "matic": "polygon", "polygon": "polygon",
    "arb": "arbitrum", "arbitrum": "arbitrum",
    "op": "optimism", "optimism": "optimism",
    "bnb": "binance_coin", "binance_coin": "binance_coin", "binance": "binance_coin",
    "sol": "solana", "solana": "solana",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "xrp": "xrp", "dot": "polkadot", "polkadot": "polkadot",
    "link": "chainlink", "chainlink": "chainlink",
    "uni": "uniswap", "uniswap": "uniswap",
    "usdt": "tether", "tether": "tether", "usdc": "usd_coin",
    "ltc": "litecoin", "litecoin": "litecoin",
    "shib": "shiba_inu", "shiba": "shiba_inu", "shiba_inu": "shiba_inu",
    "atom": "cosmos", "cosmos": "cosmos",
    "near": "near", "ftm": "fantom", "fantom": "fantom",
    "trx": "tron", "tron": "tron",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_entities(value: object) -> list[str]:
    """Parse the dataset's parenthesized comma-separated new_coins field."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    s = str(value).strip().lower()
    s = s.strip("()[]{} ")
    if not s:
        return []
    out = []
    for part in re.split(r"[,;|/]", s):
        token = re.sub(r"[^a-z0-9_-]+", "", part.strip())
        if token and token not in out:
            out.append(token)
    return out


def normalize(token: str) -> tuple[str, str]:
    token = token.lower().strip()
    if token in ALIASES:
        return ALIASES[token], "canonical_alias"
    return token, "unresolved_raw"


def week_start(ts: pd.Timestamp) -> pd.Timestamp:
    # ISO Monday bins, with the first/last bins retained when they intersect
    # the requested June-August audit interval.
    return (ts - pd.Timedelta(days=int(ts.weekday()))).normalize()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(SRC, dtype={"created_at": "string", "new_coins": "string"})
    parsed = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    if parsed.isna().any():
        raise RuntimeError(f"unparseable created_at rows: {int(parsed.isna().sum())}")
    df["created_at_utc"] = parsed
    df["week_start_utc"] = df["created_at_utc"].map(week_start)
    audit_start = pd.Timestamp("2022-06-01", tz="UTC")
    audit_end = pd.Timestamp("2022-09-01", tz="UTC")
    focus = df[(df.created_at_utc >= audit_start) & (df.created_at_utc < audit_end)].copy()

    # One row per source post/entity mention, retaining raw and normalized forms.
    entity_rows = []
    raw_counter, norm_counter, kind_counter = Counter(), Counter(), Counter()
    for i, row in focus.iterrows():
        raw_entities = parse_entities(row.get("new_coins"))
        for raw in raw_entities:
            normalized, kind = normalize(raw)
            raw_counter[raw] += 1
            norm_counter[normalized] += 1
            kind_counter[kind] += 1
            entity_rows.append({
                "source_row": int(i),
                "created_at_utc": row.created_at_utc.isoformat(),
                "week_start_utc": row.week_start_utc.date().isoformat(),
                "raw_entity": raw,
                "normalized_entity": normalized,
                "normalization_kind": kind,
                "sentiment_type": str(row.sentiment_type),
                "compound": float(row.compound),
                "full_text": str(row.full_text),
            })
    write_csv(OUT / "normalized_entities.csv", entity_rows,
              ["source_row", "created_at_utc", "week_start_utc", "raw_entity", "normalized_entity", "normalization_kind", "sentiment_type", "compound", "full_text"])

    # Weekly post counts for all focus weeks intersecting June-August.
    weeks = pd.date_range(week_start(audit_start), week_start(audit_end - pd.Timedelta(seconds=1)), freq="7D", tz="UTC")
    weekly_posts, weekly_entities, weekly_sent = [], [], []
    for ws in weeks:
        we = ws + pd.Timedelta(days=7)
        g = focus[(focus.created_at_utc >= ws) & (focus.created_at_utc < we)]
        eg = [r for r in entity_rows if r["week_start_utc"] == ws.date().isoformat()]
        weekly_posts.append({"week_start_utc": ws.date().isoformat(), "week_end_exclusive_utc": we.isoformat(), "post_count": int(len(g)), "positive_posts": int((g.sentiment_type == "POSITIVE").sum()), "neutral_posts": int((g.sentiment_type == "NEUTRAL").sum()), "negative_posts": int((g.sentiment_type == "NEGATIVE").sum()), "posts_with_entity_field": int(sum(bool(parse_entities(x)) for x in g.new_coins))})
        weekly_entities.append({"week_start_utc": ws.date().isoformat(), "week_end_exclusive_utc": we.isoformat(), "entity_mention_count": len(eg), "distinct_raw_entities": len({x["raw_entity"] for x in eg}), "distinct_normalized_entities": len({x["normalized_entity"] for x in eg}), "canonical_alias_mentions": sum(x["normalization_kind"] == "canonical_alias" for x in eg), "unresolved_raw_mentions": sum(x["normalization_kind"] == "unresolved_raw" for x in eg)})
        weekly_sent.append({"week_start_utc": ws.date().isoformat(), "post_count": int(len(g)), "mean_compound": round(float(g.compound.mean()), 6) if len(g) else None, "median_compound": round(float(g.compound.median()), 6) if len(g) else None, "positive_share": round(float((g.sentiment_type == "POSITIVE").mean()), 6) if len(g) else None, "neutral_share": round(float((g.sentiment_type == "NEUTRAL").mean()), 6) if len(g) else None, "negative_share": round(float((g.sentiment_type == "NEGATIVE").mean()), 6) if len(g) else None})
    write_csv(OUT / "weekly_post_counts.csv", weekly_posts, list(weekly_posts[0]))
    write_csv(OUT / "weekly_entity_counts.csv", weekly_entities, list(weekly_entities[0]))
    write_csv(OUT / "sentiment_summary.csv", weekly_sent, list(weekly_sent[0]))

    # Raw-field and temporal coverage audit.
    missing = {c: int(df[c].isna().sum()) for c in df.columns if c != "created_at_utc" and c != "week_start_utc"}
    event_bounds = {}
    if EVENTS.exists():
        min_t, max_t, n, contracts = None, None, 0, set()
        with EVENTS.open() as f:
            for line in f:
                if not line.strip():
                    continue
                x = json.loads(line); n += 1
                t = pd.Timestamp(x["block_timestamp"], tz="UTC")
                min_t = t if min_t is None or t < min_t else min_t
                max_t = t if max_t is None or t > max_t else max_t
                if x.get("token_contract_address"):
                    contracts.add(str(x["token_contract_address"]).lower())
        event_bounds = {"event_file": str(EVENTS), "event_sha256": sha256(EVENTS), "event_rows": n, "event_min_utc": min_t.isoformat() if min_t is not None else None, "event_max_utc": max_t.isoformat() if max_t is not None else None, "distinct_token_contract_addresses": len(contracts), "contract_to_entity_map_present": False}

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "source": str(SRC),
        "source_sha256": sha256(SRC),
        "source_rows": int(len(df)),
        "source_columns": [c for c in df.columns if c not in {"created_at_utc", "week_start_utc"}],
        "source_time_min_utc": df.created_at_utc.min().isoformat(),
        "source_time_max_utc": df.created_at_utc.max().isoformat(),
        "focus_interval": {"start_inclusive_utc": audit_start.isoformat(), "end_exclusive_utc": audit_end.isoformat()},
        "focus_post_count": int(len(focus)),
        "focus_week_count": len(weeks),
        "focus_entity_mention_count": len(entity_rows),
        "distinct_raw_entity_count": len(raw_counter),
        "distinct_normalized_entity_count": len(norm_counter),
        "normalization_kind_counts": dict(kind_counter),
        "top_raw_entities": raw_counter.most_common(30),
        "top_normalized_entities": norm_counter.most_common(30),
        "missing_values_all_source": missing,
        "author_identity_field_present": False,
        "wallet_author_crosswalk_used": False,
        "future_interaction_fields_policy": {"favorite_count": "audit_only_excluded_from_asof_features", "reply_count": "audit_only_excluded_from_asof_features", "retweet_count": "audit_only_excluded_from_asof_features", "importance_coefficient": "audit_only_excluded_from_asof_features"},
        "entity_join_policy": "No contract-to-symbol/protocol map is available in this artifact; normalized text entities must not be treated as matched to token_contract_address.",
        "canonical_aliases": ALIASES,
        "event_alignment": event_bounds,
        "limitations": ["CSV does not expose a reliable author/handle field.", "new_coins is a noisy precomputed entity field with aliases and multi-entity strings.", "The current chain event file has contract addresses but no frozen contract-to-symbol/protocol mapping.", "This audit does not establish that any wallet saw, read, or was causally influenced by a post."],
    }
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    report = f'''# Influencer context audit (2026-09-28)\n\n## Scope\n\nThis is a deterministic audit of the frozen Crypto Influencer v5 CSV before it is used as **public market context**. It does not call an LLM, identify wallet owners, or claim that a wallet read any post.\n\n- Source rows: **{len(df):,}**\n- Source time range: **{df.created_at_utc.min().date()} to {df.created_at_utc.max().date()}**\n- June--August 2022 focus interval: **{len(focus):,} posts** across **{len(weeks)} ISO weeks**\n- Entity mentions in focus interval: **{len(entity_rows):,}**\n- Distinct raw entity strings: **{len(raw_counter):,}**\n- Distinct normalized strings: **{len(norm_counter):,}**\n\n## Interpretation boundary\n\nThe dataset has no reliable author/handle column, so it is treated as anonymous public market narrative. The precomputed engagement fields (`favorite_count`, `reply_count`, `retweet_count`) and importance fields are retained for audit only and excluded from any as-of feature unless a historical snapshot policy is later established.\n\n`new_coins` is parsed conservatively. A small frozen alias table maps common ticker/name variants (for example, `btc` and `bitcoin`) to a canonical label. Unresolved strings remain unresolved; no fuzzy matching is performed.\n\nThe chain event file currently contains token contract addresses but this artifact has **no contract-to-symbol/protocol map**. Therefore normalized post entities are not yet joined to wallet history. The next safe integration step is either a frozen mapping with provenance or a weaker text-side entity experiment explicitly labeled as unmatched-to-chain.\n\n## Weekly coverage\n\nSee `weekly_post_counts.csv`, `weekly_entity_counts.csv`, and `sentiment_summary.csv`. These use Monday 00:00 UTC ISO-week bins and retain partial edge weeks intersecting June 1--August 31, 2022.\n\n## Files\n\n- `weekly_post_counts.csv`: post and sentiment counts by week.\n- `weekly_entity_counts.csv`: raw/normalized entity coverage by week.\n- `normalized_entities.csv`: post-level entity audit with source row, timestamp, and text.\n- `sentiment_summary.csv`: weekly sentiment summaries.\n- `dataset_manifest.json`: hashes, schema, missingness, policy, and chain-alignment limits.\n\n## Status\n\n**Audit complete; predictive integration not yet claimed.**\n'''
    (OUT / "REPORT.md").write_text(report)
    print(json.dumps({"output": str(OUT), "focus_posts": len(focus), "focus_weeks": len(weeks), "entity_mentions": len(entity_rows), "status": "PASS"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
