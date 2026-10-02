"""Canonical physical-event history and bounded, independently checked proofs."""
from __future__ import annotations
from collections import Counter, defaultdict
from functools import lru_cache
import json, math
import numpy as np
import pandas as pd
from certificate_v2 import CAPS, stable_id, verify, roles_for, certificate_features

DAY = 86400
COLS = ['block_timestamp', 'block_number', 'transaction_index', 'transaction_hash',
        'event_index', 'event_family', 'from_address', 'to_address', 'value_lossless',
        'quantity', 'token_contract_address', 'trace_address_json', 'error',
        'receipt_status', 'receipt_contract_address']

def canonicalize(role_rows):
    e = role_rows[COLS].copy()
    for c in COLS:
        if c not in ('block_timestamp', 'block_number', 'transaction_index', 'event_index', 'receipt_status'):
            e[c] = e[c].fillna('').astype(str)
    for c in ('block_number', 'transaction_index', 'event_index', 'receipt_status'):
        e[c] = pd.to_numeric(e[c], errors='coerce').fillna(-1).astype('int64')
    e['block_timestamp'] = pd.to_datetime(e.block_timestamp, utc=True)
    e['timestamp'] = epoch_seconds(e.block_timestamp)
    keys = ['transaction_hash','event_family','event_index','trace_address_json',
            'from_address','to_address','token_contract_address','value_lossless','quantity']
    e = e.drop_duplicates(keys).sort_values(['block_number','transaction_index','event_family','event_index','trace_address_json'], kind='stable').reset_index(drop=True)
    return e

def epoch_seconds(values):
    """Normalize resolution explicitly: pandas 3 may preserve microseconds."""
    stamps = pd.to_datetime(values, utc=True)
    if stamps.isna().any():
        raise ValueError('Missing event timestamp')
    return stamps.dt.as_unit('s').astype('int64')


class History:
    def __init__(self, canonical, cutoff, deleted=()):
        self.cutoff = cutoff
        self.ts = int(pd.Timestamp(cutoff, tz='UTC').timestamp())
        expected = epoch_seconds(canonical.block_timestamp)
        if not np.array_equal(expected.to_numpy(), canonical.timestamp.to_numpy()):
            raise ValueError('Ledger timestamp unit mismatch: rebuild epoch seconds from block_timestamp')
        self.df = canonical[canonical.block_timestamp < pd.Timestamp(cutoff, tz='UTC')]
        assert (self.df.timestamp < self.ts).all()
        if deleted:
            self.df = self.df.drop(index=list(deleted), errors='ignore')
        self.source_indices = self.df.index.to_numpy()
        self.df = self.df.reset_index(drop=True)
        self.a = {c: self.df[c].to_numpy() for c in self.df.columns}
        self.out = self.df.groupby('from_address', sort=False).indices
        self.inc = self.df.groupby('to_address', sort=False).indices
        self.event_map = {}
        self.audit = Counter()
        self.contracts = set(self.df.token_contract_address) | set(self.df.receipt_contract_address)
        self.contracts.discard('')
        self.global_cache = {}
        self.token_cache = {}

    def actor(self, w):
        return np.union1d(self.out.get(w, []), self.inc.get(w, [])).astype('int64')

    def compact(self, i):
        d = {k: self.a[k][i].item() if isinstance(self.a[k][i], np.generic) else self.a[k][i]
             for k in COLS if k != 'block_timestamp'}
        d['timestamp'] = int(self.a['timestamp'][i])
        d['block_timestamp'] = pd.Timestamp(self.a['block_timestamp'][i]).isoformat()
        assert int(pd.Timestamp(d['block_timestamp']).timestamp()) == d['timestamp']
        d['event_id'] = stable_id(d)
        self.event_map[d['event_id']] = i
        return d

    def lookup(self, eid):
        i = self.event_map.get(eid)
        return None if i is None else self.compact(i)

    def global_stat(self, c):
        if c in self.global_cache:
            return self.global_cache[c]
        ids = self.actor(c)
        if len(ids) == 0:
            v = (0, 0, 0, 0., 0)
        else:
            t = self.a['timestamp'][ids]; tx = self.a['transaction_hash'][ids]
            peers = set(self.a['from_address'][ids]) | set(self.a['to_address'][ids]); peers.discard(c)
            v = (len(set(tx)), len(set(tx[t >= self.ts-30*DAY])), len(set(tx[t >= self.ts-7*DAY])),
                 (self.ts-int(t.min()))/DAY, len(peers))
        self.global_cache[c] = v
        return v

    def tokens(self, c):
        if c in self.token_cache:
            return self.token_cache[c]
        d = defaultdict(list)
        for i in self.actor(c)[::-1]:
            if self.a['event_family'][i] != 'token_transfer':
                continue
            tok = self.a['token_contract_address'][i]
            if tok and len(d[tok]) < CAPS['token_actor_tail']:
                d[tok].append(int(i))
        self.token_cache[c] = dict(d)
        return self.token_cache[c]

    def proofs(self, case):
        w, pool = case['wallet'], set(case['pool'])
        result = defaultdict(list); used = defaultdict(set); kindn = Counter()
        def add(c, kind, i, j, **kw):
            if c not in pool or c == w or kindn[(c,kind)] >= CAPS['proofs_per_kind']:
                return
            tx = {self.a['transaction_hash'][i], self.a['transaction_hash'][j]}
            self.audit['proposals'] += 1
            if len(tx) != 2 or tx & used[c]:
                self.audit['same_or_reused_transaction_rejected'] += 1
                return
            p = dict(case_id=case['case_id'], wallet=w, candidate=c, cutoff=case['cutoff'], cutoff_ts=self.ts,
                     kind=kind, roles=roles_for(kind), events=[self.compact(i),self.compact(j)], **kw)
            ok, reasons = verify(p, self.lookup)
            if not ok:
                self.audit['invalid_proposals'] += 1
                for r in reasons: self.audit['rejected_'+r] += 1
                return
            p['proof_id'] = stable_id({'transaction_hash': case['case_id']+'|'+c+'|'+kind,
                                       'event_index': '|'.join(e['event_id'] for e in p['events'])})
            result[c].append(p); used[c].update(tx); kindn[(c,kind)] += 1
            self.audit['accepted_'+kind] += 1
        # Paths first: fixed priority is independent of labels and scores.
        peers = defaultdict(list)
        for i in self.out.get(w, np.array([],dtype=int))[::-1]:
            p = self.a['to_address'][i]
            if p == w: continue
            if p not in peers and len(peers) >= CAPS['path_peers']: continue
            if len(peers[p]) < CAPS['wallet_events_per_peer']: peers[p].append(int(i))
        for p, wis in peers.items():
            for j in self.out.get(p, np.array([],dtype=int))[-CAPS['peer_tail']:][::-1]:
                c = self.a['to_address'][j]
                if c not in pool or c in (w,p): continue
                for i in wis:
                    if (self.a['block_number'][i],self.a['transaction_index'][i]) < (self.a['block_number'][j],self.a['transaction_index'][j]) and self.a['timestamp'][i] <= self.a['timestamp'][j]:
                        add(c,'ordered_path',i,int(j),peer=p)
        wt = self.tokens(w)
        top = sorted(wt, key=lambda t:(-self.a['timestamp'][wt[t][0]],t))[:CAPS['wallet_tokens']]
        for c in sorted(pool):
            if c == w: continue
            ct = self.tokens(c)
            for tok in top:
                if kindn[(c,'shared_token_wedge')] >= CAPS['proofs_per_kind']: break
                if tok not in ct: continue
                for i in wt[tok]:
                    if kindn[(c,'shared_token_wedge')] >= CAPS['proofs_per_kind']: break
                    for j in ct[tok]:
                        if kindn[(c,'shared_token_wedge')] >= CAPS['proofs_per_kind']: break
                        add(c,'shared_token_wedge',i,j,token=tok)
        pairs = defaultdict(list)
        for i in self.actor(w)[::-1]:
            c = self.a['to_address'][i] if self.a['from_address'][i] == w else self.a['from_address'][i]
            if c in pool and len(pairs[c]) < 24: pairs[c].append(int(i))
        for c, ids in pairs.items():
            for k,i in enumerate(ids):
                for j in ids[k+1:]: add(c,'repeat_interaction',j,i)
        return dict(result)

    def features(self, case, proofs):
        w, pool = case['wallet'], case['pool']
        ids = self.actor(w); pairs = defaultdict(list)
        for i in ids:
            c = self.a['to_address'][i] if self.a['from_address'][i] == w else self.a['from_address'][i]
            pairs[c].append(int(i))
        outids = self.out.get(w,np.array([],dtype=int))
        outtx = len(set(self.a['transaction_hash'][outids]))
        freq = Counter(self.a['to_address'][outids]); total = sum(freq.values())
        entropy = -sum((n/max(1,total))*math.log(n/max(1,total)) for n in freq.values()) / max(1.,math.log(max(1,len(freq))))
        native = [i for i in ids if self.a['event_family'][i] != 'token_transfer']
        def logv(i):
            try: return math.log1p(max(0.,float(self.a['value_lossless'][i])))
            except (ValueError, OverflowError): return 0.
        wmean = np.mean([logv(i) for i in native]) if native else 0.
        wg = self.global_stat(w); wb = (wg[2]+.5)/(wg[1]/4+.5)
        B=np.zeros((len(pool),12),np.float32); C=np.zeros((len(pool),12),np.float32); E=np.zeros((len(pool),15),np.float32)
        for k,c in enumerate(pool):
            q = np.asarray(pairs.get(c,[]),dtype='int64')
            qo=q[self.a['from_address'][q]==w]; qi=q[self.a['to_address'][q]==w]
            no=len(set(self.a['transaction_hash'][qo])); ni=len(set(self.a['transaction_hash'][qi]))
            g,g30,g7,age,degree=self.global_stat(c)
            last=math.exp(-(self.ts-int(self.a['timestamp'][qo].max()))/(90*DAY)) if len(qo) else 0.
            B[k]=[no>0,math.log1p(no),last,math.log1p(ni),no>0 and ni>0,math.log1p(g),math.log1p(g30),math.log1p(g7),math.log1p(age),math.log1p(outtx),math.log1p(len(freq)),entropy]
            C[k]=certificate_features(proofs.get(c,[]),self.ts)
            nq=[i for i in q if self.a['event_family'][i]!='token_transfer']
            counts=Counter(self.a['value_lossless'][nq]); rep=max(counts.values(),default=0)
            fail=sum(bool(self.a['error'][i]) or self.a['receipt_status'][i]==0 for i in q)
            known=sum(bool(self.a['error'][i]) or self.a['receipt_status'][i]>=0 for i in q)
            tq=[i for i in q if self.a['event_family'][i]=='token_transfer']; balances=defaultdict(lambda:[0.,0.])
            for i in tq:
                try: amount=max(0.,float(self.a['quantity'][i]))
                except (ValueError,OverflowError): amount=0.
                if not math.isfinite(amount): amount=0.
                balances[self.a['token_contract_address'][i]][0 if self.a['from_address'][i]==w else 1]+=amount
            flow=[(v[0]-v[1])/(v[0]+v[1]) for v in balances.values() if v[0]+v[1]>0]
            traces=[i for i in q if self.a['event_family'][i]=='internal_trace']; depths=[]
            for i in traces:
                try: depths.append(len(json.loads(self.a['trace_address_json'][i])))
                except (ValueError,TypeError): pass
            E[k]=[(np.mean([logv(i) for i in nq])-wmean) if nq else 0., math.log1p(rep if rep>=2 else 0), bool(nq),wb,(g7+.5)/(g30/4+.5),fail/max(1,len(q)),known/max(1,len(q)),
                  sum(self.a['from_address'][i]==w for i in tq)/max(1,len(tq)),sum(self.a['to_address'][i]==w for i in tq)/max(1,len(tq)),np.mean(flow) if flow else 0.,math.log1p(len(balances)),len(traces)/max(1,len(q)),np.mean(depths) if depths else 0.,c in self.contracts,math.log1p(degree)]
        assert np.isfinite(B).all() and np.isfinite(C).all() and np.isfinite(E).all()
        return B,C,E
