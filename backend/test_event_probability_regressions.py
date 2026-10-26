import unittest
import event_direction
import event_scenario_board as board


class ProbabilityRegressions(unittest.TestCase):
    def row(self, title, direction=1, status='DIRECTIONAL', ident='a'):
        return dict(id=ident, title=title, weight=.8, direction=direction,
                    direction_status=status, geographic_relation='DIRECT_SCOPE')

    def pathway(self, rows, name):
        return next(x for x in board.candidates(rows, 'GDP growth', 'World', '30 days')['ranked_scenarios'] if x['id']==name)

    def test_support_for_mild_pathway_must_increase_not_decrease_odds(self):
        row=self.pathway([self.row('GDP recovery improves')], 'mixed_recovery')
        self.assertGreater(row['experimental_probability']['probability_estimate'], .5)
        self.assertEqual(row['supporting_source_count'], 1)

    def test_opposition_reduces_estimate_and_duplicate_does_not_raise_it(self):
        positive=self.row('GDP recovery improves')
        first=self.pathway([positive], 'mixed_recovery')['experimental_probability']
        duplicate=self.pathway([positive, positive], 'mixed_recovery')['experimental_probability']
        mixed=self.pathway([positive,self.row('GDP contracts', -1, ident='b')], 'mixed_recovery')['experimental_probability']
        self.assertEqual(first, duplicate)
        self.assertLess(mixed['probability_estimate'], first['probability_estimate'])

    def test_stability_has_an_estimate_only_for_explicit_stability(self):
        stable=self.pathway([self.row('GDP stays stable',0,'NEUTRAL')], 'stable')
        self.assertGreater(stable['experimental_probability']['probability_estimate'], .5)
        unknown=self.pathway([self.row('GDP report released',0,'UNKNOWN')], 'stable')
        self.assertIsNone(unknown['experimental_probability'])

    def test_labor_metric_direction_and_calendar_month(self):
        for title, factor, expected in [('Unemployment rises','Labor market',-1),
                                        ('Unemployment falls','Labor market',1),
                                        ('Payroll rises','Labor market',1),
                                        ('Inflation rises in May','Inflation',-1)]:
            with self.subTest(title=title):
                self.assertEqual(event_direction.inspect(title,'',factor)['direction'], expected)

    def test_forecasts_are_not_observed_events(self):
        for title in ['GDP is expected to rise','GDP will rise','GDP may rise']:
            self.assertEqual(event_direction.inspect(title,'','GDP growth')['direction_status'],'UNCONFIRMED')
