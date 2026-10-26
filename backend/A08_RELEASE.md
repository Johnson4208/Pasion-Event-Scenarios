# A08 completed OHLCV and causal VSA

market/technical.py is the shared adapter to the existing single technical.py implementation. Admin OHLCV and research endpoints use it; Stock Analytics now displays a compact completed-bar context using the same endpoint as Indicators/VSA. No duplicate RVOL calculation or probability conversion introduced. Calculation version a08-v1 records these additions.

Adds population-SD20 Bollinger bands (SMA20 +/- 2*SD20), close-location fraction CLV (Close-Low)/(High-Low), neutral .5 on valid zero-range bars and prior-only 60-session support/resistance alongside 20-session zones. Existing Wilder RSI/ATR, MFI, OBV, CMF, MACD and SMA history gates retained. CMF uses its signed money-flow multiplier; this is distinct from the 0..1 close-location fraction. Prior20 volume excludes current bar: 100 history/current400 => 4.0.

Admission validates optional trading_status TRADING/NO_TRADE/HALTED/MISSING against volume. Legacy submissions infer observed positive/zero/missing classification; HALTED requires explicit source status and zero volume. Negative volume is invalid. No trade/halts cannot originate VSA events. Zero and missing remain distinct; volume diagnostics retain prior policy. Source/venue/IANA timezone/calendar/raw-vs-adjusted corporate-action metadata and immutable snapshot clocks/hashes remain required. Completion is the reviewed provider's assertion, not an independently installed exchange-calendar feed.

Failed up-breakout event requires a prior completed close above pre-breakout resistance followed by a later close below it. It is timestamped only at the later failure bar, with known-at context gating. Trap Radar displays those observed failures, not earlier Spring/Upthrust candidates or a future label. Existing VSA candidates and later follow-through remain tentative evidence; no forced Wyckoff phase, historic confidence probability or measured order-flow narrative. Failure rule is a constrained heuristic, not a calibrated universal trap detector; downward-breakout/longer-window variants remain future reviewed rules.

Thresholds remain explicit heuristic policies after prior-only RVOL; no out-of-sample calibration was invented. Missing SMA200 suppresses its dependent strength rule. Trading quantities remain withheld pending shared F07 account/lot/cash/quote checks. No broker/order functionality added.

Validation: 3 A08 tests cover RVOL/zero-range/volume semantics, bands/history gates and later-only failed breakout. All 5 existing technical tests passed. Stock/Indicators browser checks and build are required before activation. No actual live OHLCV provider or exchange completeness was certified.

Activation checks completed: all 3 focused F05/F06 browser checks and production build passed, with the existing bundle-size warning. Local project restarted with A08 active. Full backend suite was not repeated for this technical-engine change.
