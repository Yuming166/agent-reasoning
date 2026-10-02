import copy, unittest
from certificate_v2 import stable_id,verify,roles_for,certificate_features

class CertificateTests(unittest.TestCase):
    def setUp(self):
        def event(tx,b,a,c):
            e=dict(transaction_hash=tx,event_family='external_tx',event_index=-1,trace_address_json='[]',
                   from_address=a,to_address=c,token_contract_address='',value_lossless='1',quantity='',
                   timestamp=b,block_number=b,transaction_index=0)
            e['event_id']=stable_id(e); return e
        self.a=event('tx1',1,'w','p');self.b=event('tx2',2,'p','c')
        self.ledger={e['event_id']:e for e in [self.a,self.b]}
        self.p=dict(kind='ordered_path',wallet='w',peer='p',candidate='c',cutoff_ts=3,
                    roles=roles_for('ordered_path'),events=[self.a,self.b])
    def test_real_path(self): self.assertEqual(verify(self.p,self.ledger.get),(True,[]))
    def test_wrong_direction(self):
        p=copy.deepcopy(self.p);p['wallet']='p';self.assertFalse(verify(p,self.ledger.get)[0])
    def test_future(self):
        p=copy.deepcopy(self.p);p['cutoff_ts']=2;self.assertIn('future_or_cutoff_event',verify(p,self.ledger.get)[1])
    def test_same_tx_cross_family(self):
        b=copy.deepcopy(self.b);b['transaction_hash']='tx1';b['event_family']='internal_trace';b['event_id']=stable_id(b)
        self.ledger[b['event_id']]=b;p=copy.deepcopy(self.p);p['events'][1]=b
        self.assertIn('same_transaction_not_independent',verify(p,self.ledger.get)[1])
    def test_fabrication(self):
        p=copy.deepcopy(self.p);p['events'][1]['event_id']='fake';self.assertFalse(verify(p,self.ledger.get)[0])
    def test_wrong_order(self):
        p=copy.deepcopy(self.p);p['events'].reverse();self.assertFalse(verify(p,self.ledger.get)[0])
    def test_tampered_payload(self):
        p=copy.deepcopy(self.p);p['events'][1]['value_lossless']='999';self.assertFalse(verify(p,self.ledger.get)[0])
    def test_no_evidence(self): self.assertEqual(certificate_features([],3),[0.]*12)

class TimestampTests(unittest.TestCase):
    def test_epoch_resolution_and_strict_cutoff(self):
        import pandas as pd
        from certificate_history_v2 import canonicalize, History, COLS
        rows=[]
        for j,t in enumerate(['2022-03-31T23:59:59Z','2022-04-01T00:00:00Z','2022-06-01T00:00:00Z']):
            row={k:'' for k in COLS}
            row.update(block_timestamp=t,block_number=j,transaction_index=0,event_index=-1,
                       receipt_status=1,transaction_hash='tx'+str(j),event_family='external_tx',
                       from_address='w',to_address='c',value_lossless='1')
            rows.append(row)
        for resolution in ['s','ms','us','ns']:
            frame=pd.DataFrame(rows)
            frame['block_timestamp']=pd.to_datetime(frame.block_timestamp,utc=True).dt.as_unit(resolution)
            ledger=canonicalize(frame)
            self.assertEqual(ledger.timestamp.iloc[0],1648771199)
            h=History(ledger,'2022-04-01')
            self.assertEqual(len(h.df),1)
            self.assertTrue(h.compact(0)['block_timestamp'].startswith('2022-03-31'))
            ledger['timestamp']//=1000
            with self.assertRaisesRegex(ValueError,'timestamp unit mismatch'):
                History(ledger,'2022-04-01')

    def test_calendar_crosscheck_rejects_bad_integer(self):
        t=CertificateTests();t.setUp()
        t.a['block_timestamp']='2022-06-01T00:00:00+00:00'
        reasons=verify(t.p,t.ledger.get)[1]
        self.assertIn('timestamp_unit_mismatch',reasons)
        self.assertIn('future_or_cutoff_calendar_event',reasons)

class ModelTests(unittest.TestCase):
    def test_unsupported_denominator(self):
        from certificate_models_v2 import ranking_metrics
        m=ranking_metrics([1,-1,6,2]);self.assertEqual(m['R@5'],.5);self.assertEqual(m['MRR@5'],.375)

    def test_bounded_and_invalid_zero(self):
        import torch
        from certificate_models_v2 import Scorer
        batch={k:torch.randn(2,7,n) for k,n in [('B',12),('C',12),('E',15)]}
        batch['ctx']=torch.randn(2,6);batch['valid']=torch.tensor([[0,1,1,0,0,1,1]]*2,dtype=torch.float)
        for name in ['bounded_residual','chain_all','minus_native','popularity_control','invalid_control']:
            model=Scorer(name)
            with torch.no_grad():
                for p in model.cert.parameters():p.fill_(100.)
                _,g,d,_,_,_=model(batch)
            self.assertLessEqual(float(d.abs().max()),2.)
            self.assertTrue(torch.equal(d[batch['valid']==0],torch.zeros_like(d[batch['valid']==0])))
            if name=='invalid_control':self.assertEqual(float(d.abs().max()),0.)

if __name__=='__main__':unittest.main()
