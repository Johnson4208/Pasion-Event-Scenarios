"""Versioned, gated Bayesian evidence revision for PASION Event Scenarios.

No lexical RSS headline can become a likelihood ratio. Train event-conditional
likelihoods on dated, resolved events, audit them outside this module and pass
them as reviewer-accepted model data. This engine does not cap posterior at 70%.
"""
import math

class ModelUnavailable(ValueError):pass

def revision(prior,evidence_groups,model):
    """Return posterior for mutually exclusive/exhaustive events, or withhold.

    prior: mapping scenario id => reviewed prior probability.
    evidence_groups: independent NEW groups with reviewed likelihood ratios.
    model: reviewed, held-out validated artifact metadata, not submitted by user.
    """
    if not isinstance(model,dict) or model.get('reviewed') is not True or model.get('holdout_validated') is not True:
        raise ModelUnavailable('CALIBRATED_MODEL_NOT_REVIEWED')
    if not isinstance(model.get('model_version'),str) or not model['model_version'].strip():
        raise ModelUnavailable('MODEL_VERSION_MISSING')
    if not isinstance(model.get('holdout_sample_count'),int) or model['holdout_sample_count']<100:
        raise ModelUnavailable('INSUFFICIENT_HOLDOUT_VALIDATION')
    if not isinstance(prior,dict) or not 2<=len(prior)<=20:
        raise ModelUnavailable('INVALID_PRIORS')
    ids=list(prior)
    try:
        probabilities=[float(prior[k]) for k in ids]
    except (ValueError,TypeError,OverflowError) as exc:raise ModelUnavailable('INVALID_PRIORS') from exc
    if any(not math.isfinite(x) or x<=0 or x>=1 for x in probabilities) or not math.isclose(sum(probabilities),1,abs_tol=1e-7):
        raise ModelUnavailable('PRIORS_NOT_CALIBRATED')
    if not isinstance(evidence_groups,list) or len(evidence_groups)>100:
        raise ModelUnavailable('INVALID_EVIDENCE_GROUPS')
    logp={k:math.log(prior[k]) for k in ids}
    used=[];seen=set()
    for group in evidence_groups:
        if not isinstance(group,dict) or not group.get('reviewed') or not group.get('independence_reviewed'):
            raise ModelUnavailable('UNVERIFIED_OR_DEPENDENT_EVIDENCE')
        group_id=group.get('group_id')
        if not isinstance(group_id,str) or not group_id or group_id in seen:raise ModelUnavailable('DUPLICATE_EVIDENCE_GROUP')
        seen.add(group_id)
        lr=group.get('likelihood_ratio')
        if not isinstance(lr,dict) or set(lr)!=set(ids):raise ModelUnavailable('LIKELIHOOD_RATIO_OUTCOME_MISMATCH')
        strength=group.get('dependence_discount',1.0)
        if isinstance(strength,bool) or not isinstance(strength,(float,int)) or not 0<strength<=1:
            raise ModelUnavailable('INVALID_DEPENDENCE_DISCOUNT')
        for key in ids:
            try:
                factor=float(lr[key])
                if not math.isfinite(factor) or not 0<factor<=1e6:raise ValueError()
            except (ValueError,TypeError,OverflowError) as exc:
                raise ModelUnavailable('INVALID_LIKELIHOOD_RATIO') from exc
            logp[key]+=strength*math.log(factor)
        used.append(group_id)
    maxlog=max(logp.values())
    exp={k:math.exp(logp[k]-maxlog) for k in ids}
    denominator=sum(exp.values())
    posterior={k:exp[k]/denominator for k in ids}
    return {'status':'CALIBRATED_MODEL_ELIGIBLE','probability_status':'ELIGIBLE_MODEL_REVIEWED',
        'model_version':model['model_version'],'prior':prior,'posterior':posterior,
        'evidence_groups':used,'holdout_sample_count':model['holdout_sample_count'],
        'method':'MULTINOMIAL_BAYES_LOG_LIKELIHOOD','warning':'Eligibility metadata does not replace ongoing prospective calibration and outcome monitoring.'}

def unavailable():
    return {'status':'UNAVAILABLE','probability_status':'UNAVAILABLE_NO_VALIDATED_EVENT_LIKELIHOODS',
        'calibrated_probability':False,'posterior':None,
        'reason':'Public RSS/GDELT headlines have no empirically validated likelihood ratios. Evidence-weighted shares are NOT probabilities.'}
