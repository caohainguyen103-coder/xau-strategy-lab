"""
Adaptive walk-forward strategy selector.

Simulates exactly what the user asked for in plain language:
  "chay hang ngay dua tren du lieu backtest 10 nam... neu thu phuong phap
   nay khong hieu qua se doi phuong phap khac... luu lai nhung phuong phap
   hieu qua va loi nhuan"

At each rebalance point (every `window` trading days), the engine looks
ONLY at data available up to that point (no lookahead), scores every
candidate strategy variant using the trailing `lookback` window, picks the
top-ranked one, and "trades" it for the next `window` days. The realized
result for that period is logged. If a different strategy tops the
ranking at the next rebalance, the engine switches ("doi phuong phap
khac") and that switch is recorded.
"""
import numpy as np
import pandas as pd

from backtest_engine import (
    STRATEGY_REGISTRY, run_backtest, score, load_daily
)


def build_position_cache(df: pd.DataFrame):
    """Pre-compute the position series for every (strategy, params) variant
    once over the full dataframe, so the walk-forward loop can just slice."""
    cache = {}
    for strat_name, spec in STRATEGY_REGISTRY.items():
        for params in spec["grid"]:
            key = (strat_name, tuple(sorted(params.items())))
            try:
                pos = spec["fn"](df, **params)
            except Exception:
                continue
            cache[key] = (strat_name, params, pos)
    return cache


def walk_forward(df: pd.DataFrame, window=63, lookback=504, min_trades_window=3):
    cache = build_position_cache(df)
    n = len(df)
    log = []
    current_choice = None

    start = lookback
    while start < n:
        end = min(start + window, n)
        train_slice = df.iloc[max(0, start - lookback):start].reset_index(drop=True)

        # rank all candidates using trailing `lookback` data only
        ranked = []
        for key, (strat_name, params, pos_full) in cache.items():
            pos_train = pos_full.iloc[max(0, start - lookback):start].reset_index(drop=True)
            if len(train_slice) < 30:
                continue
            try:
                res = run_backtest(train_slice, pos_train)
            except Exception:
                continue
            s = score(res, min_trades=5)
            ranked.append((s, strat_name, params, res))
        if not ranked:
            start = end
            continue
        ranked.sort(key=lambda r: r[0], reverse=True)
        best_score, best_name, best_params, best_train_res = ranked[0]

        switched = current_choice is not None and (best_name, tuple(sorted(best_params.items()))) != current_choice
        current_choice = (best_name, tuple(sorted(best_params.items())))

        # apply chosen strategy on the OUT-of-sample forward window [start, end)
        fwd_slice = df.iloc[start:end].reset_index(drop=True)
        key = (best_name, tuple(sorted(best_params.items())))
        pos_full = cache[key][2]
        pos_fwd = pos_full.iloc[start:end].reset_index(drop=True)
        try:
            fwd_res = run_backtest(fwd_slice, pos_fwd)
        except Exception:
            start = end
            continue

        log.append({
            "period_start": df["date"].iloc[start].strftime("%Y-%m-%d"),
            "period_end": df["date"].iloc[end - 1].strftime("%Y-%m-%d"),
            "strategy": best_name,
            "params": best_params,
            "switched": switched,
            "selection_score": round(best_score, 3),
            "realized_return_pct": fwd_res.total_return_pct,
            "realized_sharpe": fwd_res.sharpe,
            "realized_max_dd_pct": fwd_res.max_drawdown_pct,
            "realized_trades": fwd_res.n_trades,
            "realized_win_rate_pct": fwd_res.win_rate_pct,
        })
        start = end

    return log


def summarize(log):
    if not log:
        return {}
    equity = 1.0
    curve = []
    for rec in log:
        equity *= (1 + rec["realized_return_pct"] / 100.0)
        curve.append({"period_end": rec["period_end"], "equity": round(equity, 4)})
    total_return_pct = (equity - 1) * 100
    n_switches = sum(1 for r in log if r["switched"])
    strat_usage = {}
    for r in log:
        strat_usage.setdefault(r["strategy"], {"periods": 0, "total_return_pct": 0.0})
        strat_usage[r["strategy"]]["periods"] += 1
        strat_usage[r["strategy"]]["total_return_pct"] += r["realized_return_pct"]
    return {
        "n_periods": len(log),
        "n_switches": n_switches,
        "adaptive_total_return_pct": round(total_return_pct, 2),
        "equity_curve": curve,
        "strategy_usage": strat_usage,
    }


if __name__ == "__main__":
    df = load_daily()
    log = walk_forward(df)
    summary = summarize(log)
    print(f"Walk-forward periods: {summary.get('n_periods')}, switches: {summary.get('n_switches')}")
    print(f"Adaptive engine total return over walk-forward span: {summary.get('adaptive_total_return_pct')}%")
    for r in log[-5:]:
        print(r)
