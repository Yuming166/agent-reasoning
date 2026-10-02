import unittest
from datetime import datetime, timezone, timedelta
from scripts.run_temporal_wallet_hypotheses_v1 import metrics, execute, verify, counterfactual

class TemporalHypothesisTests(unittest.TestCase):
    def setUp(self):
        self.cut='2022-08-01T00:00:00+00:00'
        self.events=[]
        for i, (days, cp, direction) in enumerate([(1,'A','outgoing'),(2,'A','outgoing'),(3,'B','incoming'),(35,'C','outgoing'),(36,'C','incoming')]):
            t=(datetime(2022,8,1,tzinfo=timezone.utc)-timedelta(days=days)).isoformat()
            self.events.append({'block_timestamp':t,'counterparty_address':cp,'direction':direction,'event_family':'external_tx','target_sequence_index':i,'transaction_hash':f'0x{i}'})
    def test_future_events_are_not_in_metrics(self):
        future={'block_timestamp':'2022-08-01T00:01:00+00:00','counterparty_address':'Z','direction':'outgoing'}
        m,_=metrics(self.events+[future],self.cut)
        self.assertEqual(m['n'],3)
        self.assertNotIn('Z', [e['counterparty_address'] for e in self.events if e['block_timestamp'] < self.cut])
    def test_zero_denominator_is_insufficient(self):
        m,_=metrics([],self.cut)
        x=execute({'op':'threshold','metric':'new_rate_30d','operator':'>=','threshold':0.5},m)
        self.assertEqual(x['status'],'insufficient')
    def test_negative_rule_is_not_certified_as_positive(self):
        m,_=metrics(self.events,self.cut)
        x=execute({'op':'threshold','metric':'top_cp_share_30d','operator':'>=','threshold':0.9},m)
        self.assertEqual(x['status'],'unsupported')
    def test_witness_and_semantic_alignment(self):
        c={'cutoff':self.cut,'history_event_count':5,'evidence':[{'evidence_id':'E1'}]}
        p={'abstain':False,'prediction':'repeat','claim_type':'repeat_concentration','rule':{'op':'threshold','metric':'top_cp_share_30d','operator':'>=','threshold':0.5},'witness_ids':['E1']}
        v=verify(p,c,self.events,self.cut)
        self.assertTrue(v['semantic_alignment']); self.assertTrue(v['witness_valid']); self.assertTrue(v['verified'])
    def test_counterfactual_has_explicit_revision_label(self):
        c={'cutoff':self.cut,'history_event_count':5,'evidence':[{'evidence_id':'E1'}]}
        p={'abstain':False,'prediction':'repeat','claim_type':'repeat_concentration','rule':{'op':'threshold','metric':'top_cp_share_30d','operator':'>=','threshold':0.5},'witness_ids':['E1']}
        cf=counterfactual(c,self.events,p)
        self.assertTrue(cf['eligible']); self.assertIn(cf['revision'],{'CHANGE','INVARIANT','WITHDRAW'})

if __name__=='__main__': unittest.main()
