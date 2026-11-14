"""Explicit, source-linked transcriptions of public reports; never demo fixtures.

These annual observations supplement provider omissions only for the matching
issuer/year and reconciled anchors. They do not become reviewer-accepted facts.
"""
from decimal import Decimal

URL='https://bctn2025.fpt.com/wp-content/uploads/2026/04/BCTN-2025.pdf'

def enrich(snapshot):
    if snapshot.get('ticker')!='FPT' or snapshot.get('market')!='VN' or snapshot.get('period_end')!='2025':
        return snapshot
    metrics=snapshot['financials']['metrics']
    anchors={'revenue':'70112825100710','net_income':'11232339450734','cfo':'10136043915911'}
    if any(metrics.get(k,{}).get('status')!='READY' or metrics[k].get('currency')!='VND' or Decimal(metrics[k]['value'])!=Decimal(v) for k,v in anchors.items()):
        return snapshot
    # PDF pages 171–172, printed pages 170–171: investing cash-flow bridge.
    parts=[-5097919349856,7314216719,-57012522823806,49164792969282,-710700052777,23532256656,2000759192153]
    if sum(parts)!=-11624743591629:
        raise ValueError('Report cash-flow bridge does not reconcile')
    def put(key,value,page,unit='currency',formula=None):
        metrics[key]={'definition_id':key,'status':'READY','value':str(value),'unit':unit,'currency':'VND',
            'period_type':'FY','period_end':'2025','period_label':'FY 2025','provider':'FPT annual report',
            'source_url':URL+'#page='+str(page),'source_ids':['FPT:2025:annual-report:page-'+str(page)],
            'origin':'PRIMARY_REPORT_TRANSCRIPTION' if not formula else 'DERIVED',
            'human_reviewed':False,'reason_codes':[],'formula':formula,
            'source_note':'Transcribed from audited consolidated statements; source document published in 2026.'}
    capex=Decimal('5097919349856');cfo=Decimal(anchors['cfo']);fcf=cfo-capex
    put('capex',capex,171)
    put('free_cash_flow',fcf,171,formula='Reported operating cash flow − cash purchases of fixed and other long-term assets')
    put('fcf_margin',fcf/Decimal(anchors['revenue'])*100,171,'%', 'Free cash flow / revenue × 100')
    put('fcf_conversion',fcf/Decimal(anchors['net_income'])*100,171,'%', 'Free cash flow / consolidated profit × 100')
    put('shares_outstanding_fy',1703507121,204,'shares')
    common=metrics.get('common_equity',{})
    if common.get('status')=='READY' and common.get('period_end')=='2025':
        put('book_value_per_share_fy',Decimal(common['value'])/Decimal(1703507121),204,'currency/share','FY owners equity / FY closing ordinary shares')
    return snapshot
