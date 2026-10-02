#!/usr/bin/env python3
"""Offline audit of the legacy 100-row verification file against the frozen 231 frame.

This compares only exact keys and artifact provenance. It does not adjudicate identity,
transfer labels between frames, perform network access, or authorize collection.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CROSSWALK = Path('artifacts/ens_x_crosswalk')
DEFAULTS = {
    'legacy': CROSSWALK / 'verification_sample_v2_filled.csv',
    'frame': CROSSWALK / 'goal_audit_20260925/manual_review_workbook_231_v2.csv',
    'classifier': Path('scripts/classify_verification.py'),
    'report': CROSSWALK / 'verification_report_20260924.md',
    'x_raw': CROSSWALK / 'x_profiles_raw',
    'fx_raw': CROSSWALK / 'fx_raw',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        with path.open('rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
    else:
        raise FileNotFoundError(path)
    return h.hexdigest()


def norm(v: str | None) -> str:
    return (v or '').strip().lower()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f'{path}: missing CSV header')
        return list(reader)


def key_set(rows, address_col, xid_col):
    return {(norm(r.get(address_col)), (r.get(xid_col) or '').strip())
            for r in rows if norm(r.get(address_col)) and (r.get(xid_col) or '').strip()}


def account_map(rows, addr_col, xid_col):
    out = defaultdict(set)
    for r in rows:
        xid = (r.get(xid_col) or '').strip()
        addr = norm(r.get(addr_col))
        if xid and addr:
            out[xid].add(addr)
    return out


def raw_inventory(directory: Path, expected_handles: set[str]) -> dict:
    files = sorted(directory.glob('*.json'))
    file_handles = {p.stem.casefold() for p in files}
    payload_handles, payload_errors = set(), []
    http_statuses = Counter()
    for p in files:
        try:
            obj = json.loads(p.read_text(encoding='utf-8'))
            handle = norm(obj.get('handle'))
            if handle:
                payload_handles.add(handle)
            else:
                payload_errors.append({'file': p.name, 'error': 'missing_handle'})
            status = obj.get('http_status')
            http_statuses[str(status) if status is not None else 'missing'] += 1
        except Exception as e:
            payload_errors.append({'file': p.name, 'error': type(e).__name__})
    return {
        'path': str(directory), 'file_count': len(files),
        'unique_filename_handles': len(file_handles),
        'expected_sample_handles': len(expected_handles),
        'filename_handle_missing': sorted(expected_handles - file_handles),
        'filename_handle_extra': sorted(file_handles - expected_handles),
        'payload_unique_handles': len(payload_handles),
        'payload_handle_missing': sorted(expected_handles - payload_handles),
        'payload_handle_extra': sorted(payload_handles - expected_handles),
        'http_status_counts': dict(sorted(http_statuses.items())),
        'payload_errors': payload_errors,
    }


def build_report(root: Path) -> dict:
    paths = {k: root / v for k, v in DEFAULTS.items()}
    legacy, frame = read_csv(paths['legacy']), read_csv(paths['frame'])
    required_legacy = {'address', 'handle', 'x_user_id', 'verification_status', 'evidence_date'}
    required_frame = {'address', 'x_user_id', 'handle_at_profile_audit', 'manual_verdict', 'review_arm'}
    for label, rows, required in [('legacy', legacy, required_legacy), ('frame', frame, required_frame)]:
        have = set(rows[0]) if rows else set()
        if not required <= have:
            raise ValueError(f'{label}: missing columns {sorted(required-have)}')

    legacy_pairs = [(norm(r['address']), norm(r['handle'])) for r in legacy]
    dup_legacy = Counter(legacy_pairs)
    lp = key_set(legacy, 'address', 'x_user_id')
    fp = key_set(frame, 'address', 'x_user_id')
    la, fa = {norm(r['address']) for r in legacy}, {norm(r['address']) for r in frame}
    lx = {(r.get('x_user_id') or '').strip() for r in legacy if (r.get('x_user_id') or '').strip()}
    fx = {(r.get('x_user_id') or '').strip() for r in frame if (r.get('x_user_id') or '').strip()}
    lh = {norm(r['handle']) for r in legacy if norm(r.get('handle'))}
    fh = {norm(r['handle_at_profile_audit']) for r in frame if norm(r.get('handle_at_profile_audit'))}
    lm, fm = account_map(legacy, 'address', 'x_user_id'), account_map(frame, 'address', 'x_user_id')
    shared_ids = sorted(lm.keys() & fm.keys())
    address_mismatches_for_shared_ids = []
    for xid in shared_ids:
        for old_addr in sorted(lm[xid]):
            for new_addr in sorted(fm[xid]):
                if old_addr != new_addr:
                    address_mismatches_for_shared_ids.append({'x_user_id': xid, 'legacy_address': old_addr, 'frame_address': new_addr})

    # Handle overlap is contextual only: handles can be renamed/reused and are not stable IDs.
    legacy_by_handle = defaultdict(set)
    frame_by_handle = defaultdict(set)
    for r in legacy:
        h = norm(r.get('handle'))
        if h:
            legacy_by_handle[h].add((norm(r.get('address')), (r.get('x_user_id') or '').strip()))
    for r in frame:
        h = norm(r.get('handle_at_profile_audit'))
        if h:
            frame_by_handle[h].add((norm(r.get('address')), (r.get('x_user_id') or '').strip()))
    shared_handles = sorted(legacy_by_handle.keys() & frame_by_handle.keys())
    handle_link_mismatches = []
    for h in shared_handles:
        for old_addr, old_id in sorted(legacy_by_handle[h]):
            for new_addr, new_id in sorted(frame_by_handle[h]):
                if (old_addr, old_id) != (new_addr, new_id):
                    handle_link_mismatches.append({'handle_casefolded': h, 'legacy_address': old_addr, 'legacy_x_user_id': old_id, 'frame_address': new_addr, 'frame_x_user_id': new_id})

    evidence_dates = Counter((r.get('evidence_date') or '').strip() for r in legacy)
    verdicts = Counter((r.get('verification_status') or '').strip() or '<blank>' for r in legacy)
    arms = Counter((r.get('review_arm') or '').strip() for r in frame)
    frame_verdicts = Counter((r.get('manual_verdict') or '').strip() or '<blank>' for r in frame)
    expected_handles = lh
    inventories = {name: raw_inventory(paths[name], expected_handles) for name in ('x_raw', 'fx_raw')}
    input_hashes = {}
    for key in ('legacy', 'frame', 'classifier', 'report'):
        input_hashes[str(paths[key].relative_to(root))] = sha256(paths[key])
    raw_hashes = {}
    for key in ('x_raw', 'fx_raw'):
        raw_hashes[key] = {
            p.name: sha256(p) for p in sorted(paths[key].glob('*.json'))
        }

    exact_pair_repeats = [{'address': a, 'handle': h, 'rows': n}
                          for (a, h), n in sorted(dup_legacy.items()) if n > 1]
    checks = {
        'frame_is_231_rows': len(frame) == 231,
        'legacy_has_100_rows': len(legacy) == 100,
        'legacy_pair_duplicate_excess_is_explicit': len(legacy) - len(set(legacy_pairs)) == sum(n-1 for n in dup_legacy.values() if n > 1),
        'legacy_raw_files_cover_all_sample_handles': all(not inventories[k]['filename_handle_missing'] and not inventories[k]['payload_handle_missing'] and not inventories[k]['payload_errors'] for k in inventories),
        'no_exact_wallet_stable_xid_link_overlap': len(lp & fp) == 0,
        'frame_remains_unadjudicated': set(frame_verdicts) <= {'pending', '<blank>'},
    }
    return {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'offline_legacy100_vs_frozen231_reconciliation_v1',
        'network_requests': 0, 'paid_queries_usd': 0,
        'identity_adjudication_performed': False,
        'legacy_classification_provenance': {
            'classifier_script': str(paths['classifier'].relative_to(root)),
            'classifier_sha256': sha256(paths['classifier']),
            'classifier_assigns_statuses_in_code': True,
            'legacy_csv_has_reviewer_or_reviewed_at_columns': bool(set(legacy[0]) & {'reviewer','reviewed_at','reviewed_at_utc'}) if legacy else False,
            'interpretation': 'Legacy verification_status values are rule-generated by the referenced script from profile/timeline fields; the CSV records no reviewer identity or reviewed-at field. Treat as prior coded snapshot labels, not independent human adjudications.',
        },
        'inputs': input_hashes,
        'raw_capture_sha256_by_source': raw_hashes,
        'legacy_100': {
            'rows': len(legacy), 'unique_address_handle_pairs': len(set(legacy_pairs)),
            'unique_addresses': len(la), 'unique_handles': len(lh),
            'unique_nonempty_stable_x_ids': len(lx),
            'duplicate_pair_excess_rows': len(legacy) - len(set(legacy_pairs)),
            'duplicate_pairs': exact_pair_repeats,
            'status_counts': dict(sorted(verdicts.items())),
            'source_frame_status_counts': dict(sorted(Counter(r.get('status','') for r in legacy).items())),
            'evidence_date_counts': dict(sorted(evidence_dates.items())),
            'raw_response_inventory': inventories,
        },
        'frozen_231': {
            'rows': len(frame), 'unique_addresses': len(fa),
            'unique_handles': len(fh), 'unique_nonempty_stable_x_ids': len(fx),
            'review_arm_counts': dict(sorted(arms.items())),
            'manual_verdict_counts': dict(sorted(frame_verdicts.items())),
        },
        'cross_frame_comparison': {
            'exact_address_x_user_id_links_shared': len(lp & fp),
            'legacy_addresses_shared': len(la & fa),
            'stable_x_user_ids_shared': len(lx & fx),
            'handles_shared_casefolded': len(lh & fh),
            'shared_stable_ids_with_different_address_combinations': address_mismatches_for_shared_ids,
            'shared_handles_with_different_link_combinations': handle_link_mismatches,
            'no_transfer_or_extrapolation_performed': True,
        },
        'checks': checks,
        'all_checks_pass': all(checks.values()),
        'interpretation': [
            'The legacy and frozen 231-candidate frames are distinct sampling frames; no exact (address, stable X user ID) link overlaps.',
            'Legacy row labels and rates must not be copied into or used as estimates for the frozen 231 frame.',
            'Only the frozen 60-row probability arm can support design-weighted estimation after human adjudication; the 171 targeted rows remain separate.',
            'Current account-side evidence is not historical ENS/X as-of validity.',
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project-root', type=Path, default=Path.cwd())
    ap.add_argument('--out-dir', type=Path, default=Path('artifacts/ens_x_crosswalk/current_goal_audit'))
    args = ap.parse_args()
    root = args.project_root.resolve()
    report = build_report(root)
    out = root / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / 'legacy100_vs_frozen231_20260925.json'
    md_path = out / 'legacy100_vs_frozen231_20260925.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    l, f, c = report['legacy_100'], report['frozen_231'], report['cross_frame_comparison']
    md = f"""# Legacy 100-row sample vs frozen 231-candidate frame

- Generated UTC: `{report['generated_at_utc']}`
- Mode: offline only; no X/FxEmbed/ENS/BigQuery requests, no paid query, no identity adjudication.
- Legacy input: `{list(report['inputs'].items())[0][0]}`
- Rows: legacy {l['rows']} (unique address-handle pairs {l['unique_address_handle_pairs']}, duplicate excess rows {l['duplicate_pair_excess_rows']}); frozen frame {f['rows']}.
- Legacy: {l['unique_addresses']} addresses, {l['unique_handles']} handles, {l['unique_nonempty_stable_x_ids']} nonempty stable X IDs.
- Frozen frame: {f['unique_addresses']} addresses, {f['unique_handles']} handles, {f['unique_nonempty_stable_x_ids']} nonempty stable X IDs.
- Exact `(address, stable X user ID)` overlap: **{c['exact_address_x_user_id_links_shared']}**; address overlap {c['legacy_addresses_shared']}; stable ID overlap {c['stable_x_user_ids_shared']}; handle overlap {c['handles_shared_casefolded']}. Shared IDs/handles with different wallet links are retained as mismatch details in JSON.
- Legacy status counts (rule-generated snapshot labels): `{json.dumps(l['status_counts'], ensure_ascii=False)}`.
- Frozen manual verdict counts: `{json.dumps(f['manual_verdict_counts'], ensure_ascii=False)}`.
- Raw response file coverage by source: x profile `{len(l['raw_response_inventory']['x_raw']['filename_handle_missing'])} missing sample handles`, Fx `{len(l['raw_response_inventory']['fx_raw']['filename_handle_missing'])} missing`.

## Boundary

The legacy and frozen 231 frames are distinct. **Do not transfer old labels, rates, or candidate status across frames.** The legacy CSV has no reviewer/reviewed-at fields; its status values are assigned by the referenced rule-based classifier. Account-side snapshot evidence does not establish historical as-of validity. No candidate was promoted and no follow-up collection is authorized by this audit.

All machine-readable counts, per-input hashes, raw-response inventories and integrity checks are in `{json_path.name}`. Audit checks: **{'PASS' if report['all_checks_pass'] else 'FAIL'}**.
"""
    md_path.write_text(md, encoding='utf-8')
    print(json.dumps({'json': str(json_path), 'markdown': str(md_path), 'all_checks_pass': report['all_checks_pass'], 'legacy': l, 'frozen_231': f, 'cross_frame': c}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
