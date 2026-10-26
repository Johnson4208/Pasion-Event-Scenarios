import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import event_outcome_data as data

NOW = datetime(2026,10,23,tzinfo=timezone.utc)


def worldbank(value=3.2):
    return json.dumps([{'pages':1,'lastupdated':'2026-10-01'},[
        {'indicator':{'id':'FP.CPI.TOTL.ZG'},'countryiso3code':'VNM','date':'2024','value':value},
        {'indicator':{'id':'FP.CPI.TOTL.ZG'},'countryiso3code':'VNM','date':'2023','value':None},
    ]]).encode()


class OutcomeDataTests(unittest.TestCase):
    def test_worldbank_preserves_missing_values_and_rejects_other_geographies(self):
        profile=data.PROFILES['vietnam-inflation']
        rows=data.parse_worldbank(worldbank(),profile)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['period'],'2024')
        self.assertIsNone(rows[0]['publication_at'])
        for raw in (worldbank().replace(b'VNM',b'USA'),worldbank().replace(b'FP.CPI.TOTL.ZG',b'OTHER'),worldbank().replace(b'"pages": 1',b'"pages": 2')):
            with self.assertRaises(data.DataUnavailable):
                data.parse_worldbank(raw,profile)

    def test_fred_is_a_latest_vintage_series_and_missing_days_do_not_become_zero(self):
        profile=data.PROFILES['us-labor']
        rows=data.parse_fred(b'observation_date,UNRATE\n2024-01-01,3.7\n2024-02-01,.\n',profile)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],3.7)
        self.assertIsNone(rows[0]['publication_at'])
        with self.assertRaises(data.DataUnavailable):
            data.parse_fred(b'observation_date,OTHER\n2024-01-01,3.7\n',profile)
        with self.assertRaises(data.DataUnavailable):
            data.parse_fred(b'observation_date,UNRATE\n2024-01-01,nan\n',profile)

    def test_ucdp_retains_uncertain_dates_and_fatality_bounds_without_claiming_latent_risk(self):
        profile=data.PROFILES['vietnam-conflict']
        record={'id':1,'country':'Vietnam','country_id':816,'date_start':'1989-01-01T00:00:00','date_end':'1989-01-05T00:00:00',
                'date_prec':2,'low':1,'best':2,'high':4}
        rows,pages=data.parse_ucdp(json.dumps({'Result':[record],'TotalPages':1}).encode(),profile)
        self.assertEqual(pages,1)
        self.assertEqual((rows[0]['low'],rows[0]['value'],rows[0]['high']),(1,2,4))
        self.assertEqual(rows[0]['period_end'],'1989-01-05')
        self.assertEqual(rows[0]['date_precision'],2)
        record['country']='Japan'
        with self.assertRaises(data.DataUnavailable):
            data.parse_ucdp(json.dumps({'Result':[record],'TotalPages':1}).encode(),profile)

    def test_immutable_revisions_and_collection_time_never_backdate_historical_knowledge(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'outcomes.sqlite3'
            with patch.object(data,'_download',return_value=worldbank()):
                first=data.collect('vietnam-inflation',NOW)
            one=data.persist(first,path)
            with patch.object(data,'_download',return_value=worldbank(3.3)):
                second=data.collect('vietnam-inflation',NOW+timedelta(days=1))
            two=data.persist(second,path)
            self.assertNotEqual(one,two)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM outcome_snapshots').fetchone()[0],2)
                records=[json.loads(row[0]) for row in db.execute('SELECT payload FROM outcome_observations ORDER BY rowid')]
                self.assertEqual([r['value'] for r in records],[3.2,3.3])
                self.assertEqual(records[0]['known_at'],NOW.isoformat())
                self.assertEqual(records[0]['adjudication_status'],'UNREVIEWED')
                raw,digest=db.execute('SELECT body,sha256 FROM outcome_raw_responses LIMIT 1').fetchone()
                self.assertEqual(raw,worldbank())
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            coverage=data.coverage('Economy','Inflation','Vietnam',path)
            self.assertEqual(coverage['status'],'COLLECTED_NEEDS_OUTCOME_REVIEW')
            self.assertFalse(coverage['point_in_time_ready'])
            self.assertFalse(coverage['probability_model_ready'])
            self.assertEqual(coverage['profiles'][0]['observation_count'],1)

    def test_transport_failure_preserves_history_and_empty_sources_do_not_become_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'outcomes.sqlite3'
            with patch.object(data,'_download',return_value=worldbank()):
                data.persist(data.collect('vietnam-inflation',NOW),path)
            with patch.object(data,'_download',side_effect=data.DataUnavailable('OUTCOME_PROVIDER_UNREACHABLE')):
                with self.assertRaises(data.DataUnavailable):
                    data.collect('vietnam-inflation',NOW+timedelta(days=1))
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM outcome_snapshots').fetchone()[0],1)
            with patch.object(data,'_download',return_value=b'observation_date,UNRATE\n2024-01-01,.\n'):
                with self.assertRaisesRegex(data.DataUnavailable,'NO_MEASURED_OUTCOMES_NOT_ZERO'):
                    data.collect('us-labor',NOW)

    def test_partial_pagination_duplicates_and_unknown_hosts_are_rejected(self):
        profile=data.PROFILES['vietnam-conflict']
        record={'id':1,'country':'Vietnam','country_id':816,'date_start':'1989-01-01','date_end':'1989-01-01','date_prec':1,'low':1,'best':2,'high':4}
        raw=json.dumps({'Result':[record],'TotalPages':2}).encode()
        with patch.object(data,'_download',side_effect=[raw,data.DataUnavailable('OUTCOME_PROVIDER_UNREACHABLE')]):
            with self.assertRaises(data.DataUnavailable):
                data.collect('vietnam-conflict',NOW)
        with patch.object(data,'_download',return_value=raw):
            with self.assertRaisesRegex(data.DataUnavailable,'DUPLICATE_OUTCOME_OBSERVATIONS'):
                data.collect('vietnam-conflict',NOW)
        with patch.object(data,'urlopen') as request:
            with self.assertRaises(data.DataUnavailable):
                data._download('https://untrusted.example/data')
            request.assert_not_called()

    def test_readiness_checks_are_read_only_and_cannot_pool_another_region(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'absent.sqlite3'
            coverage=data.coverage('Economy','Inflation','Vietnam',path)
            self.assertEqual(coverage['status'],'NOT_COLLECTED')
            self.assertFalse(path.exists())
            coverage=data.coverage('Economy','Inflation','Japan',path)
            self.assertEqual(coverage['status'],'NO_MAPPED_OUTCOME_SOURCE')
            self.assertEqual(coverage['profiles'],[])


if __name__ == '__main__':
    unittest.main()
