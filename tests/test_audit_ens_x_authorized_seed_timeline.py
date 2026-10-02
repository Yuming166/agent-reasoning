import unittest
from datetime import datetime, timezone
from scripts.audit_ens_x_authorized_seed_timeline import analyze_tweets

START=datetime(2026,1,1,tzinfo=timezone.utc)
END=datetime(2026,2,1,tzinfo=timezone.utc)

def row(owner,tid,kind,**kw):
    return {'queried_user_id':owner,'timeline_owner_id_verified':owner,
            'source_author_id':kw.pop('source_author_id',owner), 'tweet_id':tid,
            'created_at_utc':kw.pop('created_at_utc','2026-01-10T00:00:00Z'),
            'post_kind':kind,'is_repost':kind=='repost','authored_text':kw.pop('authored_text','text'),**kw}

class TestAuthorizedSeedTimelineAudit(unittest.TestCase):
    def test_authored_kinds_and_reposts_are_separated(self):
        ids={'1','2'}
        rows=[row('1','a','original'),row('1','b','quote',quoted_author_id='2'),
              row('1','c','repost',source_author_id='2'),row('2','d','reply',replying_to_tweet_id='b')]
        x=analyze_tweets(ids,rows,START,END)
        self.assertEqual(x['counts']['1']['authored_posts'],2)
        self.assertEqual(x['counts']['1']['repost_observations'],1)
        self.assertEqual(x['counts']['2']['authored_posts'],1)
        self.assertEqual(len(x['edge_records']),2)
        self.assertEqual({e['event_type'] for e in x['edge_records']},{'quote','reply_resolved_in_local_confirmed_corpus'})
        self.assertEqual(x['edge_records'][1]['target_x_user_id'],'1')

    def test_duplicate_owner_post_counted_once_and_bad_source_rejected(self):
        ids={'1','2'}
        rows=[row('1','a','original'),row('1','a','original'),
              row('2','bad','quote',source_author_id='1',quoted_author_id='1')]
        x=analyze_tweets(ids,rows,START,END)
        self.assertEqual(x['counts']['1']['authored_posts'],1)
        self.assertEqual(x['bad_owner'],1)
        self.assertEqual(x['input_rows'],3)

    def test_out_of_window_and_missing_time_do_not_count(self):
        ids={'1'}
        rows=[row('1','old','original',created_at_utc='2025-12-31T23:59:59Z'),
              row('1','none','original',created_at_utc='')]
        x=analyze_tweets(ids,rows,START,END)
        self.assertEqual(x['counts']['1']['authored_posts'],0)
        self.assertEqual(x['out_window'],1)
        self.assertEqual(x['missing_time'],1)

if __name__=='__main__': unittest.main()
