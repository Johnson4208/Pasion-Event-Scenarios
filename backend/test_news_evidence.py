import copy
import sqlite3
import unittest
from datetime import datetime,timezone,timedelta
import news_evidence as news


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('CREATE TABLE accounts(email TEXT PRIMARY KEY)')
        self.db.executemany('INSERT INTO accounts VALUES (?)',[('one',),('two',)])
        self.now=datetime(2026,10,13,tzinfo=timezone.utc)
        for key in ('a','b','c'):
            news.register(self.db,{'id':key,'name':key,'source_url':f'https://{key}.example.com','permission_basis':'Licensed test fixture',
                'coverage':'Test issuer','permitted':True,'max_gap_seconds':3600},self.now-timedelta(days=1))
    def tearDown(self):self.db.close()
    def article(self,key='a',title='Earnings announcement',now=None,revision='original',url=None):
        return news.ingest(self.db,{'source_id':key,'url':url or f'https://{key}.example.com/story','title':title,'summary':'Reported change',
            'category':'Earnings','tickers':['TEST'],'claims':[{'text':'Revenue grew','excerpt':'Revenue increased year on year','locator':'Paragraph 2'}],
            'revision':revision,'published_at':self.now.isoformat(),'ingested_at':self.now.isoformat()},now or self.now)['article']
    def review(self,target,other,stance='SUPPORTING',now=None):
        return news.review(self.db,{'article_id':target['id'],'claim_id':target['claims'][0]['id'],
            'relations':[{'article_id':other['id'],'claim_id':other['claims'][0]['id'],'stance':stance,'explanation':'Compared reported figures'}],
            'review_note':'Human comparison'},now or self.now)
    def proposal(self,a):
        return {'article_id':a['id'],'claim_id':a['claims'][0]['id'],'ticker':'TEST','driver':'Revenue growth','proposed_change':'Review operating assumptions','rationale':'New reported context'}

    def test_source_permission_domain_and_future_gate(self):
        with self.assertRaises(ValueError):news.register(self.db,{'permitted':False},self.now)
        with self.assertRaises(ValueError):self.article(url='https://unauthorized.example.com/story')
        with self.assertRaises(ValueError):self.article(now=self.now-timedelta(seconds=1))
        self.assertEqual(news.feed(self.db,'one',now=self.now)['articles'],[])
        self.assertTrue(all(p['status']=='GAP' for p in news.feed(self.db,'one',now=self.now)['coverage']))

    def test_known_time_revision_and_gap(self):
        a=self.article();later=self.now+timedelta(hours=2)
        updated=self.article(title='Corrected announcement',revision='corrected',now=later)
        past=news.feed(self.db,'one',self.now.isoformat(),later)
        self.assertEqual(past['articles'][0]['id'],a['id'])
        self.assertEqual(news.feed(self.db,'one',now=later)['articles'][0]['id'],updated['id'])
        after=news.feed(self.db,'one',now=later+timedelta(hours=2));self.assertEqual(after['coverage'][0]['status'],'GAP')
        self.assertEqual(after['articles'][0]['claims'][0]['review']['status'],'INSUFFICIENT')

    def test_duplicate_clusters_are_not_corroboration(self):
        a=self.article();b=self.article('b',title=' EARNINGS   ANNOUNCEMENT ')
        self.assertEqual(a['cluster_id'],b['cluster_id'])
        with self.assertRaises(ValueError):self.review(a,b)
        with self.assertRaises(ValueError):self.article(url='https://a.example.com/story?utm_source=test')

    def test_claim_status_and_review_origin(self):
        a=self.article();b=self.article('b','Issuer filing');c=self.article('c','Correction notice')
        later=self.now+timedelta(minutes=1);self.review(a,b,now=later)
        self.assertEqual(news.feed(self.db,'one',self.now.isoformat(),later)['articles'][0]['claims'][0]['review']['status'],'INSUFFICIENT')
        target=next(r for r in news.feed(self.db,'one',now=later)['articles'] if r['id']==a['id'])
        self.assertEqual(target['claims'][0]['review']['status'],'SUPPORTED')
        data={'article_id':a['id'],'claim_id':a['claims'][0]['id'],'relations':[
            {'article_id':b['id'],'claim_id':b['claims'][0]['id'],'stance':'SUPPORTING','explanation':'Supports'},
            {'article_id':c['id'],'claim_id':c['claims'][0]['id'],'stance':'REFUTING','explanation':'Refutes'}],'review_note':'Conflict'}
        news.review(self.db,data,later+timedelta(minutes=1))
        target=next(r for r in news.feed(self.db,'one',now=later+timedelta(minutes=1))['articles'] if r['id']==a['id'])
        self.assertEqual(target['claims'][0]['review']['status'],'CONFLICTING')
        self.review(a,c,'REFUTING',later+timedelta(minutes=2))
        target=next(r for r in news.feed(self.db,'one',now=later+timedelta(minutes=2))['articles'] if r['id']==a['id'])
        self.assertEqual(target['claims'][0]['review']['status'],'REFUTED')

    def test_private_bookmarks_and_supported_proposal_no_baseline_change(self):
        a=self.article();b=self.article('b','Issuer filing')
        news.bookmark(self.db,'one',{'article_id':a['id'],'saved':True})
        self.assertEqual(news.feed(self.db,'two',now=self.now)['bookmarks'],[])
        with self.assertRaises(ValueError):news.propose(self.db,'one',self.proposal(a),self.now)
        self.review(a,b);p=news.propose(self.db,'one',self.proposal(a),self.now)['proposal']
        self.assertEqual(p['valuation_policy'],'NO_AUTOMATIC_BASELINE_CHANGE')
        self.assertEqual(news.proposals(self.db,'two')['proposals'],[])
        d=news.decide(self.db,{'proposal_id':p['id'],'decision':'APPROVED_FOR_DRIVER_REVIEW','note':'Check operating bridge'},self.now)
        self.assertEqual(d['decision']['valuation_policy'],'SEPARATE_F04_ASSUMPTION_REVIEW_REQUIRED')
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='valuation_assumptions'").fetchone())

    def test_later_counterevidence_blocks_driver_approval(self):
        a=self.article();b=self.article('b','Issuer filing');self.review(a,b)
        p=news.propose(self.db,'one',self.proposal(a),self.now)['proposal'];later=self.now+timedelta(minutes=1)
        self.review(a,b,'REFUTING',later)
        with self.assertRaises(ValueError):news.decide(self.db,{'proposal_id':p['id'],'decision':'APPROVED_FOR_DRIVER_REVIEW','note':'Approve'},later)
        original=news.proposals(self.db,'one')['proposals'][0]
        self.assertEqual(original['claim']['review']['status'],'SUPPORTED')

    def test_revised_corroboration_withholds_status_and_bookmarked_revision_survives(self):
        a=self.article();b=self.article('b','Issuer filing');self.review(a,b)
        news.bookmark(self.db,'one',{'article_id':a['id'],'saved':True})
        later=self.now+timedelta(minutes=1);self.article('b','Revised issuer filing',later,'corrected')
        current=next(r for r in news.feed(self.db,'one',now=later)['articles'] if r['id']==a['id'])
        self.assertEqual(current['claims'][0]['review']['status'],'INSUFFICIENT')
        self.article('a','Revised announcement',later+timedelta(minutes=1),'corrected')
        old=next(r for r in news.feed(self.db,'one',now=later+timedelta(minutes=1))['articles'] if r['id']==a['id'])
        self.assertTrue(old['superseded']);self.assertEqual(old['claims'][0]['review']['status'],'INSUFFICIENT')
