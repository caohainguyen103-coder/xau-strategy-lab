"""
Auto-managed pool of the "core" (originally hand-designed) XAU/USD trading
strategy families used by the daily research engine.

CORE_STRATEGY_REGISTRY follows the same shape as AI_STRATEGY_REGISTRY in
ai_strategies.py:

    CORE_STRATEGY_REGISTRY["Some Strategy Name"] = {
        "fn": some_function,      # (df, **params) -> pd.Series of -1/0/1
        "grid": [ {param combo}, ... ],
    }

Starting 2026-09-05, this file is reviewed and edited AUTOMATICALLY by the
daily scheduled job (see automation/strategy_registry_state.json for the
per-family performance streaks that drive these decisions, and its
"changelog" list for a full history of every automatic change and why it
was made):
  - A family that misses the top-20 out-of-sample leaderboard AND has a
    non-positive walk-forward contribution for bad_streak_threshold_days
    (see strategy_registry_state.json "config") consecutive daily runs is
    removed, UNLESS doing so would drop the registry below "min_families".
  - A family that stays in the top-20 leaderboard AND keeps a non-negative
    walk-forward contribution for good_streak_threshold_days consecutive
    daily runs gets a few extra nearby parameter combinations added to its
    grid (bounded by "max_variants_per_family" and "max_total_variants"),
    to search for more profit in a region that has already proven
    productive.
Every automatic change is validated (the job re-imports this exact file and
checks CORE_STRATEGY_REGISTRY is non-empty and well-formed) before being
committed -- if validation fails, the change is discarded and logged as
"failed_validation" in strategy_registry_state.json, and this file is left
untouched.

This file is meant to be edited by the automation job, not by hand -- but
nothing bad happens if you read it or edit it yourself, as long as
automation/strategy_registry_state.json stays consistent with it (same set
of family names as keys under "families").
"""
import numpy as np
import pandas as pd


def sma(s, n): return s.rolling(n, min_periods=n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False, min_periods=n).mean()

def atr(df, n):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high-low), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def bollinger(s, n, k):
    mid = sma(s, n); std = s.rolling(n, min_periods=n).std()
    return mid - k*std, mid, mid + k*std

def donchian(df, n):
    return df["low"].rolling(n, min_periods=n).min(), df["high"].rolling(n, min_periods=n).max()


def strat_sma_cross(df, fast, slow):
    f, s = sma(df["close"], fast), sma(df["close"], slow)
    pos = pd.Series(np.where(f > s, 1, -1), index=df.index)
    pos[f.isna() | s.isna()] = 0
    return pos

def strat_ema_cross(df, fast, slow):
    f, s = ema(df["close"], fast), ema(df["close"], slow)
    pos = pd.Series(np.where(f > s, 1, -1), index=df.index)
    pos[f.isna() | s.isna()] = 0
    return pos

def strat_bb_breakout(df, n, k):
    lower, mid, upper = bollinger(df["close"], n, k)
    close = df["close"]; pos = pd.Series(0, index=df.index)
    pos[close > upper] = 1; pos[close < lower] = -1
    pos = pos.replace(0, np.nan).ffill().fillna(0)
    pos[mid.isna()] = 0
    return pos

def strat_donchian_breakout(df, n):
    lower, upper = donchian(df, n)
    close = df["close"]; pos = pd.Series(0, index=df.index)
    pos[close >= upper.shift(1)] = 1; pos[close <= lower.shift(1)] = -1
    pos = pos.replace(0, np.nan).ffill().fillna(0)
    pos[upper.isna() | lower.isna()] = 0
    return pos

def strat_atr_trend(df, ema_n, atr_n, mult):
    e = ema(df["close"], ema_n); a = atr(df, atr_n)
    upper_band = e + mult*a; lower_band = e - mult*a
    close = df["close"]; pos_arr = np.zeros(len(df), dtype=int); state = 0
    for i in range(len(df)):
        c, ub, lb = close.iloc[i], upper_band.iloc[i], lower_band.iloc[i]
        if np.isnan(ub) or np.isnan(lb): pos_arr[i] = 0; continue
        if c > ub: state = 1
        elif c < lb: state = -1
        pos_arr[i] = state
    return pd.Series(pos_arr, index=df.index)


CORE_STRATEGY_REGISTRY = {
    "SMA Crossover": {"fn": strat_sma_cross, "grid": [{"fast": f, "slow": s} for f in (3,5,7,10,15,20) for s in (30,40,50,60,75) if f<s]},
    "EMA Crossover": {"fn": strat_ema_cross, "grid": [{"fast": f, "slow": s} for f in (3,5,8,10,12,15,20) for s in (26,35,40,50,60,75) if f<s]},
    "Bollinger Breakout": {"fn": strat_bb_breakout, "grid": [{"n": n, "k": k} for n in (10,14,17,20,25,30,40) for k in (1.5,1.75,2.0,2.25,2.5)]},
    "Donchian Breakout": {"fn": strat_donchian_breakout, "grid": [{"n": n} for n in (10,15,20,25,30,40,55,75,100)]},
    "ATR Trend (Keltner-style)": {"fn": strat_atr_trend, "grid": [{"ema_n": e, "atr_n": a, "mult": m} for e in (15,20,25) for a in (7,10,14) for m in (1.25,1.5,1.75)]},
}
