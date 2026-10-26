"""A06 deterministic industrial operating statement and cash-flow waterfall."""
from decimal import Decimal

REQUIRED=('revenue_growth','ebit_margin','tax_rate','da_pct','capex_pct','nwc_pct','interest_pct','nci_income_pct','net_borrowing_pct')

def operating_year(revenue,opening_nwc,drivers,cash_date,currency):
    if any(k not in drivers for k in REQUIRED):raise ValueError('MISSING_OPERATING_FORECAST_DRIVER')
    d={k:Decimal(str(drivers[k])) for k in REQUIRED}
    if any(not v.is_finite() for v in d.values()):raise ValueError('INVALID_OPERATING_DRIVER')
    if any(not 0<=d[k]<=1 for k in REQUIRED if k not in ('revenue_growth','net_borrowing_pct')):raise ValueError('INVALID_OPERATING_DRIVER_RANGE')
    revenue=Decimal(str(revenue))*(1+d['revenue_growth']);opening_nwc=Decimal(str(opening_nwc))
    if revenue<=0 or not opening_nwc.is_finite():raise ValueError('INVALID_OPERATING_BASE')
    ebit=revenue*d['ebit_margin'];tax=ebit*d['tax_rate'];da=revenue*d['da_pct'];capex=revenue*d['capex_pct']
    closing_nwc=revenue*d['nwc_pct'];delta=closing_nwc-opening_nwc
    interest=revenue*d['interest_pct'];nci=revenue*d['nci_income_pct'];borrowing=revenue*d['net_borrowing_pct']
    common=ebit-interest-max(Decimal(0),ebit-interest)*d['tax_rate']-nci
    if revenue-ebit-da<0:raise ValueError('NEGATIVE_IMPLIED_OPERATING_COSTS')
    fcff=ebit-tax+da-capex-delta;fcfe=common+da-capex-delta+borrowing
    amounts={'revenue':revenue,'ebit':ebit,'tax':tax,'da':da,'capex':capex,'opening_nwc':opening_nwc,'closing_nwc':closing_nwc,
        'delta_nwc':delta,'interest':interest,'nci_income':nci,'net_income_common':common,'net_borrowing':borrowing,'fcff':fcff,'fcfe':fcfe,
        'operating_costs_before_da':revenue-ebit-da}
    return {**{k:str(v) for k,v in amounts.items()},'cash_date':cash_date,'currency':currency,'origin':'FORECAST',
        'revenue_basis':'REVIEWED_AGGREGATE_REVENUE_GROWTH_DRIVER','cost_basis':'MARGIN_IMPLIED_AGGREGATE_COSTS_NOT_SEGMENT_COGS',
        'tax_policy':'EXPLICIT_RATE_NO_TAX_LOSS_CARRYFORWARD_MODEL',
        'waterfall':{'fcff':{'after_tax_ebit':str(ebit-tax),'da':str(da),'capex':str(-capex),'delta_nwc':str(-delta)},
            'fcfe':{'common_income':str(common),'da':str(da),'capex':str(-capex),'delta_nwc':str(-delta),'net_borrowing':str(borrowing)}},
        'reconciliation':{'fcff_difference':'0','fcfe_difference':'0'},'calculation_version':'a06-v1'}
