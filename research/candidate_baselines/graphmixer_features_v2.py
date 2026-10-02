"""Match the original GraphMixer outgoing-role semantics on expanded pools."""
import numpy as np
import pandas as pd


def outgoing_index(role, cutoff, wallets):
    t = pd.Timestamp(cutoff, tz='UTC')
    q = role[(role.direction == 'outgoing') & role.counterparty_address.ne('')
             & role.target_address.ne('') & (role.block_timestamp < t)]
    counts = q.counterparty_address.value_counts()
    recent = q.loc[q.block_timestamp >= t-pd.Timedelta(days=30), 'counterparty_address'].value_counts()
    own = {}
    for wallet, rows in q[q.target_address.isin(wallets)].groupby('target_address', sort=False):
        own[wallet] = (rows.counterparty_address.value_counts(),
                       rows.groupby('counterparty_address').block_timestamp.max())
    return t, counts, recent, own


def candidate_matrix(index, wallet, pool):
    t, counts, recent, own = index
    freq, last = own.get(wallet, ({}, {}))
    rows = []
    for candidate in pool:
        n = int(freq.get(candidate, 0))
        age = min(365., max(0., (t-last[candidate]).total_seconds()/86400)) if n else 365.
        rows.append([np.log1p(counts.get(candidate, 0)), np.log1p(recent.get(candidate, 0)),
                     np.log1p(n), np.log1p(age), float(n > 0)])
    return np.asarray(rows, dtype=np.float32)
