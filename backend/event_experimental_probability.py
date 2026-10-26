"""Transparent *experimental* binary scenario probability proxy.

This is NOT the validated Bayesian forecasting engine. The generic news pathways lack
historically estimated base rates and event-conditional likelihoods, so this
module uses an EXPLICIT, uninformative assumed prior and a deterministic
bounded headline-evidence log-odds update.

The resulting numbers are sensitivity-dependent *experimental probability
estimates*, never calibrated, empirical probabilities or investment signals.
For unsupported pathways, no number is returned. Evidence independence is
not established; a capped effective source count makes this conservative.
"""
import math

VERSION="event-probability-experimental-v2"
ASSUMED_PRIOR=.50
MAX_EFFECTIVE_CLUSTERS=3
LOG_ODDS_PER_UNIT=1.25

def _number(value,default=0.):
    if isinstance(value,bool):return default
    try:
        x=float(value)
        return x if math.isfinite(x) else default
    except (TypeError,ValueError,OverflowError):return default

def _logit(p):
    return math.log(p/(1-p))

def _sigmoid(x):
    if x>=0:return 1/(1+math.exp(-x))
    k=math.exp(x)
    return k/(1+k)

def estimate(sources,target,scenario_id):
    """Inputs are already filtered to unique, directly relevant story clusters.

    'agreement' is signed pathway evidence in [-1,1], *not* a measured
    likelihood ratio. We expose calculations and prior sensitivity instead
    of claiming reliability from model outputs. Never use future information.
    """
    if not sources:return None
    filtered=[]
    seen=set()
    for item in sources:
        if not isinstance(item,dict):continue
        group=str(item.get("cluster_id") or item.get("id") or "").strip()
        if not group or group in seen:continue
        seen.add(group)
        weight=max(0.,min(1.,_number(item.get("weight"))))
        if weight<=0:continue
        # Use the audited pathway contribution, not numeric distance from the
        # pathway label. A positive report must never penalize a mild positive
        # pathway (the old distance formula did exactly that).
        role=item.get("evidence_role")
        if role not in ("SUPPORTS", "CHALLENGES"):
            continue
        contribution=_number(item.get("contribution"))
        if (role=="SUPPORTS" and contribution<=0) or (role=="CHALLENGES" and contribution>=0):
            continue
        if item.get("geographic_relation") in ("EXTERNAL_CONTEXT", "UNVERIFIED_SCOPE"):
            continue
        agreement=max(-1.,min(1.,contribution/max(1e-9,_number(item.get("weight")))))
        filtered.append((weight,agreement,group))
    if not filtered:return None
    # Group by story (not by syndicated article). Independence remains UNKNOWN;
    # cap the effective corroboration multiplier, and use mean signal.
    signal=sum(weight*agreement for weight,agreement,_ in filtered)/max(1e-9,sum(x[0] for x in filtered))
    weighted_coverage=sum(x[0] for x in filtered)/len(filtered)
    effective_count=min(MAX_EFFECTIVE_CLUSTERS,math.sqrt(len(filtered)))
    delta=LOG_ODDS_PER_UNIT*signal*weighted_coverage*effective_count
    result=_sigmoid(_logit(ASSUMED_PRIOR)+delta)
    sensitivity=[_sigmoid(_logit(p)+delta) for p in (.25,.75)]
    return {
        "status":"EXPERIMENTAL_UNCALIBRATED",
        "model_version":VERSION,
        "scenario_id":scenario_id,
        "probability_estimate":round(result,4),
        "assumed_prior":ASSUMED_PRIOR,
        "prior_sensitivity_range":[round(min(sensitivity),4),round(max(sensitivity),4)],
        "evidence_cluster_count":len(filtered),
        "effective_cluster_count":round(effective_count,3),
        "net_lexical_signal":round(signal,4),
        "log_odds_change":round(delta,4),
        "quality":"LOW_UNVALIDATED_INPUT" if len(filtered)<3 else "UNVALIDATED_INPUT",
        "calibrated":False,
        "assumptions":{
            "prior":"Equal prior odds 50/50 for each nonexclusive event. NOT a historical base rate.",
            "direction":"Audited supporting/opposing pathway contributions from headline rules; interpretation may be wrong.",
            "evidence":"Only explicitly aligned story clusters; source independence unverified.",
            "update":"sigmoid(logit(prior) + 1.25 * weighted directional signal * min(3,sqrt(n))).",
        },
        "warning":"Experimental, assumption-sensitive number. NOT validated event likelihood or a real-world probability."
    }
