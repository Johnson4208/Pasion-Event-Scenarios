from dataclasses import dataclass
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo

def instant(value):
    if not isinstance(value,str):raise ValueError('Offset-aware clock required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Offset-aware clock required')
    return result.astimezone(timezone.utc)

def eligible_at_origin(known_at,origin):return instant(known_at)<=instant(origin)
def derived_known_at(inputs):
    values=list(inputs)
    if not values:raise ValueError('Input clocks required')
    return max(values,key=instant)

@dataclass(frozen=True)
class InformationClocks:
    published_at:str
    ingested_at:str
    accepted_at:str
    def __post_init__(self):
        for value in (self.published_at,self.ingested_at,self.accepted_at):instant(value)
    @property
    def known_at(self):return derived_known_at((self.published_at,self.ingested_at,self.accepted_at))

@dataclass(frozen=True)
class MarketSession:
    venue:str
    timezone:str
    session_date:str
    opens_at:str
    closes_at:str
    complete:bool
    def __post_init__(self):
        zone=ZoneInfo(self.timezone);day=date.fromisoformat(self.session_date)
        opened,closed=instant(self.opens_at),instant(self.closes_at)
        if not self.venue or opened>=closed or opened.astimezone(zone).date()!=day or not isinstance(self.complete,bool):raise ValueError('Invalid venue session')
    def bar_eligible(self,as_of,known_at,origin):
        return self.complete and instant(self.opens_at)<=instant(as_of)<=instant(self.closes_at)<=instant(origin) and eligible_at_origin(known_at,origin)

@dataclass(frozen=True)
class ForecastHorizon:
    unit:str
    count:int
    def __post_init__(self):
        if self.unit not in ('COMPLETED_SESSIONS','CALENDAR_DAYS','ISSUER_FISCAL_YEARS') or isinstance(self.count,bool) or not isinstance(self.count,int) or self.count<=0:raise ValueError('Explicit horizon unit required')
