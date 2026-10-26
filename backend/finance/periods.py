from dataclasses import dataclass
from datetime import date,timedelta

@dataclass(frozen=True)
class AccountingPeriod:
    issuer:str
    fiscal_year:str
    basis:str
    start:str
    end:str
    def __post_init__(self):
        if not self.issuer or not self.fiscal_year or self.basis not in ('Q','YTD','FY','TTM') or date.fromisoformat(self.start)>date.fromisoformat(self.end):raise ValueError('Invalid issuer accounting period')

@dataclass(frozen=True)
class BalanceAsOf:
    issuer:str
    date:str
    def __post_init__(self):
        if not self.issuer:raise ValueError()
        date.fromisoformat(self.date)

def validate_calendar(calendar):
    start,end=date.fromisoformat(calendar['start']),date.fromisoformat(calendar['end'])
    quarters=[date.fromisoformat(v) for v in calendar['quarter_ends']]
    if len(quarters)!=4 or start>quarters[0] or not all(a<b for a,b in zip(quarters,quarters[1:])) or quarters[-1]!=end or not str(calendar['year']):raise ValueError('Explicit fiscal boundaries required')
    return calendar

def quarter_start(calendar,index):
    validate_calendar(calendar)
    if not 0<=index<4:raise ValueError()
    return calendar['start'] if index==0 else (date.fromisoformat(calendar['quarter_ends'][index-1])+timedelta(days=1)).isoformat()

def contiguous(quarters):
    return len(quarters)==4 and all(date.fromisoformat(a['period_end'])+timedelta(days=1)==date.fromisoformat(b['period_start']) for a,b in zip(quarters,quarters[1:]))
