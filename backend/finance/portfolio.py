"""A11 reconciled-return primitives and explicit hypothetical risk diagnostics."""
from decimal import Decimal

def twr(periods):
    if not periods or any(p.get('reconciled') is not True or p.get('external_flows_complete') is not True for p in periods):return {'status':'UNAVAILABLE','value':None,'reason':'RECONCILED_FLOW_SEGMENTED_PERIODS_REQUIRED'}
    result=Decimal(1)
    for previous,current in zip(periods,periods[1:]):
        if previous['end']!=current['start']:return {'status':'UNAVAILABLE','value':None,'reason':'NONCONTIGUOUS_RETURN_PERIODS'}
    for p in periods:
        opening,closing=Decimal(str(p['opening_value'])),Decimal(str(p['closing_before_external_flow']))
        if not opening.is_finite() or not closing.is_finite() or opening<=0 or closing<0:raise ValueError('Invalid reconciled valuation')
        result*=closing/opening
    return {'status':'READY','value':str(result-1),'unit':'fraction','basis':'RECONCILED_EXTERNAL_FLOW_SEGMENTS'}

def drawdown(values):
    if not values:return {'status':'UNAVAILABLE','value':None}
    data=[Decimal(str(v)) for v in values]
    if any(not v.is_finite() or v<=0 for v in data):raise ValueError()
    peak=data[0];worst=Decimal(0)
    for v in data:peak=max(peak,v);worst=min(worst,v/peak-1)
    return {'status':'READY','value':str(worst),'unit':'fraction'}

def stress(holdings,cash,shock='-.2'):
    holdings,cash,shock=map(lambda x:Decimal(str(x)),(holdings,cash,shock))
    if any(not v.is_finite() for v in (holdings,cash,shock)) or holdings<0 or cash<0 or shock<-1:raise ValueError()
    return {'status':'HYPOTHETICAL','holdings_shock':str(shock),'pnl':str(holdings*shock),'post_stress_value':str(holdings*(1+shock)+cash),
        'policy':'UNIFORM_HOLDINGS_PRICE_SHOCK_CONSTANT_FX_CASH_UNCHANGED_NOT_A_FORECAST'}
