#!/usr/bin/env python3
"""Resume local-model stance labeling on the original 12-account seed posts."""
import json
import sys
from pathlib import Path

ROOT = Path('/storage/gaoym/ex-graph-microtransaction-analysis')
sys.path.insert(0, str(ROOT / 'scripts'))
import ens_x_overnight_sentiment as sentiment  # noqa: E402

sentiment.OUT = ROOT / 'artifacts/ens_x_crosswalk/paper_dataset_tiered_20260926'
sentiment.SOURCE = ROOT / 'artifacts/ens_x_crosswalk/overnight_ai_dataset_20260926/x_authored_posts_observed.jsonl'
original_classify = sentiment.classify


def classify_seed(post):
    result = original_classify(post)
    result['identity_tier'] = 'strict_account_side_reviewed_snapshot'
    return result


sentiment.classify = classify_seed
sentiment.main()
summary_path = sentiment.OUT / 'sentiment_summary.json'
summary = json.loads(summary_path.read_text(encoding='utf-8'))
summary['limitations'] = [
    'AI stance labels are model features, not human gold labels.',
    'The original 12 wallet-to-X links are current account-side snapshots and have not been historically reconstructed.',
    'Only observed account-authored posts are labeled; timeline coverage may be truncated.',
]
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
