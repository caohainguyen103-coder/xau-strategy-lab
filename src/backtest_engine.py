"""
XAU/USD Strategy Research & Backtesting Engine
Data source: TradingView chart layout "Nguyen 7" (OANDA:XAUUSD), exported via
TradingView's native "Download chart data" feature (Table view).

This engine:
  1. Loads OHLCV daily data (~12 years) for OANDA:XAUUSD.
  2. Generates a family of classic technical strategies with parameter grids.
  3. Backtests every variant with realistic execution (signal on close[t],
     execution on open[t+1], transaction cost in bps).
  4. Splits data into an in-sample (train) window and out-of-sample (test)
     window and ranks strategies by out-of-sample risk-adjusted performance.
  5. Writes a full leaderboard + the current "best" strategy + its live
     recommendation to results.json (consumed by the web dashboard).
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DAILY_CSV = "../data/xauusd_daily.csv"
TRADING_DAYS_PER_YEAR = 252
COST_BPS = 5.0  # round-trip transaction cost approximation (spread+slippage), in basis points of price
RISK_FREE = 0.0

# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def load_daily(path=DAILY_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={"time": "ts"})
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)
    df = df[["date", "open", "high", "low", "close", "Volume"]]
    df.columns = ["date", "open", "high", "low", "close", "volume"]
    return df


# ----------------------------------------------------------------------------
# Indicators
# ----------------------------------------------------------------------------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def macd(s: pd.Series, fast: int, slow: int, signal: int):
    macd_line = ema(s, fast) - ema(s, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def bollinger(s: pd.Series, n: int, k: float):
    mid = sma(s, n)
    std = s.rolling(n, min_periods=n).std()
    return mid - k * std, mid, mid + k * std


def donchian(df: pd.DataFrame, n: int):
    upper = df["high"].rolling(n, min_periods=n).max()
    lower = df["low"].rolling(n, min_periods=n).min()
    return lower, upper


# ----------------------------------------------------------------------------
# Strategy library: each returns a position Series in {-1, 0, 1} indexed like df,
# representing the *desired* position after the close of each bar (executed
# at next bar's open).
# ----------------------------------------------------------------------------

def strat_sma_cross(df, fast, slow):
    f, s = sma(df["close"], fast), sma(df["close"], slow)
    pos = np.where(f > s, 1, -1)
    pos = pd.Series(pos, index=df.index)
    pos[f.isna() | s.isna()] = 0
    return pos


def strat_ema_cross(df, fast, slow):
    f, s = ema(df["close"], fast), ema(df["close"], slow)
    pos = np.where(f > s, 1, -1)
    pos = pd.Series(pos, index=df.index)
    pos[f.isna() | s.isna()] = 0
    return pos


def strat_rsi_meanrev(df, n, low_th, high_th):
    r = rsi(df["close"], n)
    pos = pd.Series(0, index=df.index)
    state = 0
    r_arr = r.values
    pos_arr = np.zeros(len(df), dtype=int)
    for i in range(len(df)):
        v = r_arr[i]
        if np.isnan(v):
            pos_arr[i] = 0
            continue
        if v < low_th:
            state = 1
        elif v > high_th:
            state = -1
        elif low_th <= v <= high_th and (state == 1 and v > 50) or (state == -1 and v < 50):
            state = 0
        pos_arrZi] = state
    return pd.Series(pos_arr, index=df.index)


def strat_macd_cross(df, fast, slow, signal):
    macd_line, signal_line, hist = macd(df["close"], fast, slow, signal)
    pos = np.where(hist > 0, 1, -1)
    pos = pd.Series(pos, index=df.index)
    pos[macd_line.isna() | signal_line.isna()] = 0
    return pos


def strat_bb_meanrev(df, n, k):
    lower, mid, upper = bollinger(df["close"], n, k)
    close = df["close"]
    pos_arr = np.zeros(len(df), dtype=int)
    state = 0
    for i in range(len(df)):
        c, lo, up, m = close.iloc[i], lower.iloc[i], upper.iloc[i], mid.iloc[i]
        if np.isnan(lo) or np.isnan(up):
            pos_arr[i] = 0
            continue
        if c < lo:
            state = 1
        elif c > up:
            state = -1
        elif (state == 1 and c > m) or (state == -1 and c < m):
            state = 0
        pos_arr[i] = state
    return pd.Series(pos_arr, index=df.index)


def strat_bb_breakout(df, n, k):
    lower, mid, upper = bollinger(df["close"], n, k)
    close = df["close"]
    pos = pd.Series(0, index=df.index)
    pos[close > upper] = 1
    pos[close < lower] = -1
    pos = pos.replace(0, np.nan).ffill().fillna(0)
    pos[mid.isna()] = 0
    return pos


def strat_donchian_breakout(df, n):
    lower, upper = donchian(df, n)
    close = df["close"]
    pos = pd.Series(0, index=df.index)
    pos[close >= upper.shift(1)] = 1
    pos[close <= lower.shift(1)] = -1
    pos = pos.replace(0, np.nan).ffill().fillna(0)
    pos[upper.isna() | lower.isna()] = 0
    return pos


def strat_momentum(df, n, threshold_pct):
    ret_n = df["close"].pct_change(n)
    pos = pd.Series(0, index=df.index)
    pos[ret_n > threshold_pct] = 1
    pos[ret_n < -threshold_pct] = -1
    pos[ret_n.isna()] = 0
    return pos


def strat_atr_trend(df, ema_n, atr_n, mult):
    e = ema(df["close"], ema_n)
    a = atr(df, atr_n)
    upper_band = e + mult * a
    lower_band = e - mult * a
    close = df["close"]
    pos_arr = np.zeros(len(df), dtype=int)
    state = 0
    for i in range(len(df)):
        c, ub, lb = close.iloc[i], upper_band.iloc[i], lower_band.iloc[i]
        if np.isnan(ub) or np.isnan(lb):
            pos_arr[i] = 0
            continue
        if c > ub:
            state = 1
        elif c < lb:
            state = -1
        pos_arr[i] = state
    return pd.Series(pos_arr, index=df.index)


STRATEGY_REGISTRY = {
    "SMA Crossover": {
        "fn": strat_sma_cross,
        "grid": [{"fast": f, "slow": s} for f in (5, 10, 20) for s in (50, 100, 200) if f < s],
    },
    "EMA Crossover": {
        "fn": strat_ema_cross,
        "grid": [{"fast": f, "slow": s} for f in (5, 8, 12, 20) for s in (26, 50, 100) if f < s],
    },
    "RSI Mean Reversion": {
        "fn": strat_rsi_meanrev,
        "grid": [
            {"n": n, "low_th": lo, "high_th": 100 - lo}
            for n in (7, 14, 21)
            for lo in (20, 25, 30)
        ],
    },
    "MACD Crossover": {
        "fn": strat_macd_cross,
        "grid": [
            {"fast": 12, "slow": 26, "signal": 9},
            {"fast": 8, "slow": 17, "signal": 9},
            {"fast": 5, "slow": 35, "signal": 5},
            {"fast": 19, "slow": 39, "signal": 9},
        ],
    },
    "Bollinger Mean Reversion": {
        "fn": strat_bb_meanrev,
        "grid": [{"n": n, "k": k} for n in (14, 20, 30) for k in (1.5, 2.0, 2.5)],
    },
    "Bollinger Breakout": {
        "fn": strat_bb_breakout,
        "grid": [{"n": n, "k": k} for n in (14, 20, 30) for k in (1.5, 2.0, 2.5)],
    },
    "Donchian Breakout": {
        "fn": strat_donchian_breakout,
        "grid": [{"n": n} for n in (10, 20, 55, 100)],
    },
    "Momentum": {
        "fn": strat_momentum,
        "grid": [{"n": n, "threshold_pct": t} for n in (5, 10, 20) for t in (0.01, 0.02, 0.03)],
    },
    "ATR Trend (Keltner-style)": {
        "fn": strat_atr_trend,
        "grid": [
            {"ema_n": e, "atr_n": a, "mult": m}
            for e in (20, 50) for a in (10, 14) for m in (1.5, 2.0, 2.5)
        ],
    },
}


# ----------------------------------------------------------------------------
# Backtest core
# ----------------------------------------------------------------------------

@dataclass
class BacktestResult:
    strategy: str
    params: dict
    n_trades: int
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    sharpe: float
    calmar: float
    avg_trade_pct: float
    equity_curve: list = field(default_factory=list)
    dates: list = field(default_factory=list)


def run_backtest(df: pd.DataFrame, pos: pd.Series, cost_bps=COST_BPS) -> BacktestResult:
    """pos[t] = desired position decided using info up to close[t].
    Executed at open[t+1]. Return realized between open[t+1] and open[t+2]
    approximated using close-to-close returns shifted by one bar (standard
    walk-forward backtest simplification), with transaction costs charged
    whenever position changes."""
    close = df["close"].values
    n = len(df)
    pos_shifted = pos.shift(1).fillna(0).values  # position held DURING bar t (decided at t-1 close, entered at t open)
    ret = np.zeros(n)
    ret[1:] = (close[1:] - close[:-1]) / close[:-1]
    strat_ret = pos_shifted * ret

    pos_change = np.abs(np.diff(np.concatenate([[0], pos_shifted])))
    cost = pos_change * (cost_bps / 10000.0)
    strat_ret_net = strat_ret - cost

    equity = np.cumprod(1 + strat_ret_net)
    total_return_pct = (equity[-1] - 1) * 100

    n_years = n / TRADING_DAYS_PER_YEAR
    cagr = (equity[-1] ** (1 / n_years) - 1) * 100 if n_years > 0 and equity[-1] > 0 else -100.0

    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / running_max
    max_dd_pct = drawdown.min() * 100

    # trade-level stats: a "trade" = a contiguous block of non-zero position
    trades = []
    cur_sign = 0
    entry_idx = None
    for i in range(n):
        p = pos_shifted[i]
        sign = np.sign(p)
        if sign != cur_sign:
            if cur_sign != 0 and entry_idx is not None:
                trades.append((entry_idx, i))
            if sign != 0:
                entry_idx = i
            else:
                entry_idx = None
            cur_sign = sign
    if cur_sign != 0 and entry_idx is not None:
        trades.append((entry_idx, n))

    trade_returns = []
    for a, b in trades:
        seg = strat_ret_net[a:b]
        trade_returns.append(np.prod(1 + seg) - 1)
    trade_returns = np.array(trade_returns) if trade_returns else np.array([0.0])

    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns <= 0]
    win_rate = (len(wins) / len(trade_returns) * 100) if len(trade_returns) > 0 else 0.0
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-9 else (float("inf") if gross_profit > 0 else 0.0)

    daily_std = strat_ret_net.std(ddof=1) if n > 1 else 0.0
    sharpe = (strat_ret_net.mean() / daily_std * math.sqrt(TRADING_DAYS_PER_YEAR)) if daily_std > 1e-12 else 0.0

    calmar = (cagr / abs(max_dd_pct)) if abs(max_dd_pct) > 1e-9 else 0.0
    avg_trade_pct = trade_returns.mean() * 100

    return BacktestResult(
        strategy="", params={},
        n_trades=len(trades),
        total_return_pct=round(total_return_pct, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        win_rate_pct=round(win_rate, 2),
        profit_factor=round(profit_factor, 3) if math.isfinite(profit_factor) else 999.0,
        sharpe=round(sharpe, 3),
        calmar=round(calmar, 3),
        avg_trade_pct=round(avg_trade_pct, 3),
        equity_curve=[round(x, 5) for x in equity.tolist()],
        dates=df["date"].dt.strftime("%Y-%m-%d").tolist(),
    )


def score(res: BacktestResult, min_trades=15) -> float:
    """Composite ranking score: primarily risk-adjusted (Calmar+Sharpe),
    penalize strategies with too few trades (overfit / not statistically
    meaningful) or catastrophic drawdown."""
    if res.n_trades < min_trades:
        return -999.0
    if res.max_drawdown_pct < -60:
        return -500.0
    return 0.5 * res.sharpe + 0.5 * (res.calmar / 2.0)


# ----------------------------------------------------------------------------
# Search: train/test split + full-period refit
# ----------------------------------------------------------------------------

def search_all(df: pd.DataFrame, train_frac=0.7, min_trades=15):
    n = len(df)
    split = int(n * train_frac)
    train_df = df.iloc[:split].reset_index(drop=True)
    test_df = df.iloc[split:].reset_index(drop=True)

    all_results = []
    for strat_name, spec in STRATEGY_REGISTRY.items():
        fn = spec["fn"]
        for params in spec["grid"]:
            try:
                pos_train = fn(train_df, **params)
                res_train = run_backtest(train_df, pos_train)
            except Exception:
                continue

            pos_full = fn(df, **params)
            res_full = run_backtest(df, pos_full)

            test_pos = pos_full.iloc[split:].reset_index(drop=True)
            try:
                res_test = run_backtest(test_df, test_pos)
            except Exception:
                continue

            all_results.append({
                "strategy": strat_name,
                "params": params,
                "train": res_train,
                "test": res_test,
                "full": res_full,
                "score_test": score(res_test, min_trades=min_trades),
                "score_train": score(res_train, min_trades=min_trades),
            })

    all_results.sort(key=lambda r: r["score_test"], reverse=True)
    return all_results, split


def latest_signal(df: pd.DataFrame, strat_name: str, params: dict) -> dict:
    fn = STRATEGY_REGISTRY[strat_name]["fn"]
    pos = fn(df, **params)
    last_pos = int(pos.iloc[-1])
    label = {1: "MUA (Long)", -1: "BÁN (Short)", 0: "ĐỨNG NGOÀI (Flat)"}[last_pos]
    return {
        "position": last_pos,
        "label": label,
        "as_of_date": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "as_of_close": float(df["close"].iloc[-1]),
    }


if __name__ == "__main__":
    df = load_daily()
    print(f"Loaded {len(df)} daily bars: {df['date'].iloc[0].date()} -> {df['date'].iloc[-1].date()}")
    results, split = search_all(df)
    print(f"Train/test split at index {split} ({df['date'].iloc[split].date()})")
    print(f"Tested {len(results)} strategy variants.")
    top = results[0]
    print("\nTOP STRATEGY (by out-of-sample score):")
    print(top["strategy"], top["params"])
    print("Test:", top["test"])
