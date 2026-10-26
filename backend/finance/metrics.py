"""A04 definition-specific profitability bases; never relabel proxies as standard."""
BASES={'operating_profit':'REPORTED_OPERATING_PROFIT_NOT_AUTOMATIC_EBIT',
       'ebit':'REVIEWED_EBIT','ebitda':'STANDARD_EBIT_PLUS_ELIGIBLE_PERIOD_DA',
       'reported_ebitda':'ISSUER_REPORTED_EBITDA','adjusted_ebitda':'ISSUER_ADJUSTED_EBITDA',
       'proxy_ebitda':'PROXY_NOT_STANDARD_EBITDA','accumulated_depreciation':'BALANCE_STOCK_NOT_PERIOD_EXPENSE',
       'roa':'NET_INCOME_OVER_AVERAGE_OPENING_CLOSING_ASSETS',
       'roe':'COMMON_INCOME_OVER_AVERAGE_COMMON_EQUITY','debt_ebitda':'ASOF_DEBT_OVER_FY_OR_TTM_STANDARD_EBITDA',
       'net_margin':'MATCHED_PERIOD_NET_INCOME_OVER_REVENUE','ebitda_margin':'MATCHED_PERIOD_STANDARD_EBITDA_OVER_REVENUE',
       'cfo_margin':'MATCHED_DURATION_CFO_OVER_REVENUE'}

def annotate(result):
    output=dict(result);key=output['definition_id']
    if key in BASES:output['basis_flags']=[BASES[key]]
    if key in ('roa','roe'):
        output['annualization_policy']='ACTUAL_SELECTED_PERIOD_RETURN_NO_FORCED_ANNUALIZATION'
    if key=='proxy_ebitda':output['origin']='PROXY'
    return output

def returns_period(result,flow):
    output=dict(result)
    if output['status']=='READY':
        output.pop('id',None)
        output.update(period_start=flow['period_start'],period_end=flow['period_end'],period_type=flow['period_type'])
    return annotate(output)
