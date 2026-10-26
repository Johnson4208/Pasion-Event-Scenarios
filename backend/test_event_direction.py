import unittest
import event_direction as direction


class ReportedDirectionTests(unittest.TestCase):
    def test_direction_depends_on_factor_and_word_boundaries(self):
        for factor, title, expected in [
            ('GDP growth', 'GDP growth declines sharply', -1),
            ('GDP growth', 'GDP growth increases rapidly', 1),
            ('GDP growth', 'GDP growth decreases', -1),
            ('Inflation', 'Inflation rises rapidly', -1),
            ('Inflation', 'Inflation cools after a rate cut', 1),
            ('Conflict risk', 'Military conflict escalates', -1),
            ('Conflict risk', 'Ceasefire brings peace deal to armed conflict', 1),
            ('GDP growth', 'GDP Việt Nam tăng trưởng mạnh', 1),
            ('Inflation', 'Lạm phát Việt Nam hạ nhiệt', 1),
        ]:
            with self.subTest(title=title):
                result = direction.inspect(title, '', factor)
                self.assertEqual(result['direction'], expected)
                self.assertEqual(result['direction_status'], 'DIRECTIONAL')

    def test_negation_and_conditional_language_are_not_asserted_evidence(self):
        for title in ['Military conflict does not escalate', 'Xung đột không leo thang',
                      'Military conflict may escalate', 'Could military conflict escalate?']:
            with self.subTest(title=title):
                result = direction.inspect(title, '', 'Conflict risk')
                self.assertEqual(result['direction'], 0)
                self.assertEqual(result['direction_status'], 'UNCONFIRMED')

    def test_unknown_is_distinct_from_explicit_stability(self):
        self.assertEqual(direction.inspect('GDP report released', '', 'GDP growth')['direction_status'], 'UNKNOWN')
        self.assertEqual(direction.inspect('GDP remains stable', '', 'GDP growth')['direction_status'], 'NEUTRAL')
        self.assertEqual(direction.inspect('GDP is not stable', '', 'GDP growth')['direction_status'], 'UNCONFIRMED')
        self.assertEqual(direction.inspect('GDP không đổi', '', 'GDP growth')['direction_status'], 'NEUTRAL')

    def test_other_topic_and_repeated_excerpt_do_not_reverse_headline(self):
        result = direction.inspect('Inflation cools but GDP declines', 'Inflation cools but GDP declines', 'Inflation')
        self.assertEqual(result['direction'], 1)
        self.assertEqual(len(result['direction_terms']), 1)


if __name__ == '__main__':
    unittest.main()
