"""Conservative, auditable headline direction. These are reported signals, not forecasts.

Unknown, conditional and negated language is withheld rather than counted as
evidence of stability. All matching uses normalized words, never substrings.
"""
import re
from event_topic_matcher import normalize, ANCHORS

VERSION = 'event-direction-v2'
UP = r'\b(?:rises?|rose|rising|increas(?:e|es|ed|ing)|surges?|surging|accelerat(?:e|es|ed|ing)|higher|tang|leo thang)\b'
DOWN = r'\b(?:falls?|fell|falling|declin(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|drops?|dropping|slows?|slowing|lower|giam|ha nhiet)\b'
IMPROVE = r'\b(?:improv(?:e|es|ed|ing|ement)|recover(?:s|ed|ing|y)?|rebounds?|expand(?:s|ed|ing)?|strengthen(?:s|ed|ing)?|phuc hoi|cai thien|mo rong)\b'
WEAKEN = r'\b(?:weaken(?:s|ed|ing)?|contract(?:s|ed|ing|ion)?|recession|shortages?|disrupt(?:s|ed|ion|ions)?|suy yeu|suy giam|suy thoai|thieu hut|gian doan|dut gay)\b'
NEUTRAL = r'\b(?:stable|steady|unchanged|flat|on hold|paus(?:e|es|ed)|on dinh|khong doi|di ngang|giu nguyen)\b'
NEGATION = r'\b(?:not|no|never|without|unlikely|khong|chua)\b(?:\s+\w+){0,3}\s*$'
CONDITIONAL = r'\b(?:could|might|may|will|expected|forecast|projected|potentially|co the|du bao|du kien|neu)\b'
RISK_FACTORS = {'Inflation', 'Energy prices', 'Healthcare costs', 'Mortgage rates',
                'Equity volatility', 'Conflict risk', 'Cybersecurity', 'Sanctions'}
ACTIVITY_FACTORS = {'GDP growth', 'Consumer demand', 'Household spending', 'Consumer confidence',
                    'Oil supply', 'Natural gas', 'Bank lending', 'Earnings outlook',
                    'Hiring plans', 'Labor market', 'M&A activity', 'Market liquidity',
                    'Risk appetite', 'Property prices', 'Commercial demand', 'Research funding',
                    'Technology adoption', 'AI adoption', 'Semiconductor supply'}


def inspect(title, description, factor):
    title_text = normalize(title)
    anchors = [normalize(x) for x in ANCHORS.get(factor, ())]
    # Prefer the headline when it names the topic. A snippet may repeat the
    # headline or describe an unrelated actor; do not count it a second time.
    text = str(title or '')
    if not any(re.search(r'\b' + re.escape(a) + r'\b', title_text) for a in anchors):
        text += '. ' + str(description or '')
    if factor in RISK_FACTORS:
        adverse, supportive = UP, DOWN
    elif factor in ACTIVITY_FACTORS:
        adverse, supportive = f'{DOWN}|{WEAKEN}', f'{UP}|{IMPROVE}'
    else:
        adverse, supportive = WEAKEN, IMPROVE
    extra_bad = extra_good = ''
    if factor == 'Conflict risk':
        extra_bad = r'\b(?:escalat(?:e|es|ed|ing|ion)|attacks?|clashes|intensif(?:y|ies|ied)|tan cong|giao tranh)\b'
        extra_good = r'\b(?:ceasefire|de escalation|deescalat(?:e|es|ion)|peace deal|ngung ban|hoa binh)\b'
    elif factor in {'Inflation', 'Energy prices', 'Healthcare costs'}:
        extra_good = r'\b(?:cools?|cooling|eas(?:e|es|ed|ing))\b'
    elif factor in {'Credit conditions', 'Central bank policy', 'Mortgage rates'}:
        extra_bad = r'\b(?:tighten(?:s|ed|ing)?|rate hikes?|raises rates|that chat|tang lai suat)\b'
        extra_good = r'\b(?:eas(?:e|es|ed|ing)|rate cuts?|cuts rates|noi long|giam lai suat)\b'
    elif factor in {'Oil supply', 'Natural gas', 'Semiconductor supply', 'Trade disruption'}:
        extra_bad = WEAKEN + r'|\b(?:cuts supply|supply cuts|port congestion|shipping delays|un tac|cham giao hang)\b'
        extra_good = IMPROVE + r'|\b(?:resumes?|restrictions lifted|khoi phuc)\b'
    patterns = [(-1, adverse + ('|' + extra_bad if extra_bad else '')),
                (1, supportive + ('|' + extra_good if extra_good else '')),
                (0, NEUTRAL)]
    matches, ignored = [], []
    clauses = re.split(r'[.;!?]|\b(?:but|however|while|whereas|nhưng|nhung|trong khi)\b', text, flags=re.I)
    anchored = [c for c in clauses if any(re.search(r'\b' + re.escape(a) + r'\b', normalize(c)) for a in anchors)]
    # Do not borrow a direction from unrelated text when the topic is absent.
    for raw in anchored if anchors else clauses:
        # A calendar month is not a modal verb ("inflation rose in May").
        clause = normalize(re.sub(r'\b(?:in|during|since|through|for) May\b', 'in month', raw))
        local_patterns = patterns
        if factor == 'Labor market' and re.search(r'\b(?:unemployment|jobless|layoffs|that nghiep)\b', clause):
            local_patterns = [(-1, UP), (1, DOWN), (0, NEUTRAL)]
        for sign, pattern in local_patterns:
            for match in re.finditer(pattern, clause):
                prefix = clause[max(0, match.start() - 60):match.start()]
                # "khong doi" explicitly means unchanged, not a negated claim.
                negated = bool(re.search(NEGATION, prefix))
                hypothetical = bool(re.search(CONDITIONAL, clause)) or '?' in text
                entry = {'term': match.group(), 'direction': sign}
                (ignored if negated or hypothetical else matches).append(entry)
    signs = {x['direction'] for x in matches}
    if -1 in signs and 1 in signs:
        status, direction = 'MIXED', 0
    elif -1 in signs:
        status, direction = 'DIRECTIONAL', -1
    elif 1 in signs:
        status, direction = 'DIRECTIONAL', 1
    elif 0 in signs:
        status, direction = 'NEUTRAL', 0
    else:
        status, direction = ('UNCONFIRMED' if ignored else 'UNKNOWN'), 0
    return {'direction': direction, 'direction_status': status,
            'direction_terms': matches, 'unconfirmed_terms': ignored,
            'direction_method': VERSION}
