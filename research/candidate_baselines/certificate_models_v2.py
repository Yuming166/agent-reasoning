"""Matched architecture certificate controls and genuinely bounded corrections."""
from __future__ import annotations
import numpy as np
import torch
from torch import nn
from certificate_v2 import EXTRA_GROUPS
from graphmixer_train import GraphMixerScorer
from motif_gated_retriever import MotifGatedScorer

VARIANTS = ['direct_global_legacy','graphmixer','legacy_motif','direct_global','certificate_only',
            'fixed_mix','candidate_gate','bounded_residual','chain_all','direct_global_chain',
            *['minus_'+g for g in EXTRA_GROUPS], 'popularity_control','invalid_control']
VARIANTS += ['legacy_cert_fusion', 'legacy_cert_nogate', 'legacy_cert_frozen', 'legacy_all_mlp']
DG_IDX = list(range(8))+list(range(14,20))

def mlp(n,hidden=32):
    return nn.Sequential(nn.Linear(n,hidden),nn.GELU(),nn.Linear(hidden,1))

class Scorer(nn.Module):
    def __init__(self,variant):
        super().__init__(); self.variant=variant
        self.base=mlp(12);self.cert=mlp(27);self.gate=mlp(25);self.chain=mlp(15)
        self.activity=mlp(6);self.open_world=mlp(6)
        if variant in ('direct_global_legacy','legacy_cert_fusion','legacy_cert_nogate','legacy_cert_frozen'):
            self.legacy=mlp(14,64)
        if variant=='legacy_all_mlp': self.legacy=mlp(20,64)
        if variant=='legacy_motif':self.legacy=MotifGatedScorer()
        if variant=='graphmixer':self.legacy=GraphMixerScorer()

    def forward(self,batch):
        b,c,e,ctx,valid=(batch[k] for k in ['B','C','E','ctx','valid'])
        v=self.variant; z=torch.zeros_like(valid)
        activity=self.activity(ctx).squeeze(-1); ow=self.open_world(ctx).squeeze(-1)
        if v=='direct_global_legacy':
            s=self.legacy(batch['X'][:,:,DG_IDX]).squeeze(-1)
            return s,z,z,s,activity,ow
        if v=='legacy_all_mlp':
            s=self.legacy(batch['X']).squeeze(-1)
            return s,z,z,s,activity,ow
        if v in ('legacy_cert_fusion','legacy_cert_nogate','legacy_cert_frozen'):
            s=self.legacy(batch['X'][:,:,DG_IDX]).squeeze(-1)
            cert=self.cert(torch.cat([c,e],dim=-1)).squeeze(-1)
            if v=='legacy_cert_fusion':
                gate=valid*torch.sigmoid(self.gate(torch.cat([b,c,e[:,:,14:15]],dim=-1)).squeeze(-1))
            else:
                gate=valid
            delta=2.*gate*torch.tanh(cert)
            return s+delta,gate,delta,s,activity,ow
        if v=='legacy_motif':
            s,_,gate,activity,ow=self.legacy(batch['X'],ctx)
            return s,gate[:,2:3].expand_as(s),z,s,activity,ow
        if v=='graphmixer':
            h=self.legacy.encode_wallet(batch['seq'])
            s=self.legacy.score_candidates(h,batch['cand_bucket'],batch['gm'])
            return s,z,z,s,self.legacy.act_head(h).squeeze(-1),self.legacy.ow_head(h).squeeze(-1)
        use_extra=v in ['chain_all','direct_global_chain','popularity_control','invalid_control'] or v.startswith('minus_')
        if not use_extra:e=torch.zeros_like(e)
        if v.startswith('minus_'):
            e=e.clone();e[:,:,EXTRA_GROUPS[v[6:]]]=0
        if v=='invalid_control': valid=z
        base=self.base(b).squeeze(-1)
        cert=self.cert(torch.cat([c,e],dim=-1)).squeeze(-1)
        gate=valid*torch.sigmoid(self.gate(torch.cat([b,c,e[:,:,14:15]],dim=-1)).squeeze(-1))
        delta=2.*gate*torch.tanh(cert)
        if v=='direct_global':gate=z;delta=z
        elif v=='certificate_only':
            score=valid*cert
            return score,valid,score,z,activity,ow
        elif v=='direct_global_chain':gate=z;delta=self.chain(e).squeeze(-1)
        elif v=='fixed_mix':gate=.5*valid;delta=gate*(cert-base)
        elif v=='candidate_gate':delta=gate*(cert-base)
        return base+delta,gate,delta,base,activity,ow

def ranking_metrics(ranks):
    """Ranks <= 0 are unsupported and contribute zero to every ALL-active mean."""
    a=np.asarray(ranks);n=len(a)
    return {'n':n,**{f'R@{k}':float(np.sum((a>0)&(a<=k))/n) if n else None for k in [5,50,100]},
            'MRR@5':float(np.sum(np.where((a>0)&(a<=5),1/np.maximum(1,a),0))/n) if n else None}
