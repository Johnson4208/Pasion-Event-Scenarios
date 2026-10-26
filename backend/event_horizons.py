"""Forecast horizons are NOT identical to news retrieval windows.

Short term: 1d, 3d, 7d, 30d, 90d. Long term: 180d, 365d, 730d.
Long-term research must accumulate news in the independent agent store.
"""
HORIZONS={
 "1 day":(1,"SHORT_TERM",7),
 "3 days":(3,"SHORT_TERM",7),
 "7 days":(7,"SHORT_TERM",7),
 "30 days":(30,"SHORT_TERM",30),
 "90 days":(90,"SHORT_TERM",45),
 "180 days":(180,"LONG_TERM",60),
 "365 days":(365,"LONG_TERM",90),
 "730 days":(730,"LONG_TERM",90)
}
LABELS={
 "1 day":"1 day","3 days":"3 days","7 days":"1 week",
 "30 days":"1 month","90 days":"3 months",
 "180 days":"6 months","365 days":"1 year","730 days":"2 years"
}
def info(horizon):
 if horizon not in HORIZONS:raise ValueError("Unsupported forecast horizon")
 days,group,lookback=HORIZONS[horizon]
 return {"horizon":horizon,"label":LABELS[horizon],"forecast_days":days,
         "timeframe":group,"news_lookback_days":lookback}
