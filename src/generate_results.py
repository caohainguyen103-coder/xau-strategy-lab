"""Runs the full search + adaptive walk-forward simulation and writes
results.json for the web dashboard."""
import json
from datetime import datetime, timezone

from backtest_engine import load_daily, search_all, latest_signal, STRATEGY_REGISTRY
from adaptive_selector import walk_forward, summarize

TOP_N = 20


def strip_curve(res):
    d = {
        "n_trades": res.n_trades,
        "total_return_pct": res.total_return_pct,
        "cagr_pct": res.cagr_pct,
        "max_drawdown_pct": res.max_drawdown_pct,
        "win_rate_pct": res.win_rate_pct,
        "profit_factor": res.profit_factor,
        "sharpe": res.sharpe,
        "calmar": res.calmar,
        "avg_trade_pct": res.avg_trade_pct,
    }
    return d


def main():
    df = load_daily()
    results, split = search_all(df)

    leaderboard = []
    for r in results[:TOP_N]:
        leaderboard.append({
            "strategy": r["strategy"],
            "params": r["params"],
            "score_test": round(r["score_test"], 3),
            "train": strip_curve(r["train"]),
            "test": strip_curve(r["test"]),
            "full": strip_curve(r["full"]),
        })

    best = results[0]
    best_equity_curve = [
        {"date": d, "equity": e}
        for d, e in zip(best["full"].dates, best["full"].equity_curve)
    ]
    # thin the curve for payload size (keep ~600 points)
    step = max(1, len(best_equity_curve) // 600)
    best_equity_curve = best_equity_curve[::step]

    live_signal = latest_signal(df, best["strategy"], best["params"])

    wf_log = walk_forward(df)
    wf_summary = summarize(wf_log)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "TradingView layout 'Nguyen 7' (OANDA:XAUUSD), daily",
        "data_range": {
            "start": df["date"].iloc[0].strftime("%Y-%m-%d"),
            "end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "n_bars": len(df),
        },
        "train_test_split_date": df["date"].iloc[split].strftime("%Y-%m-%d"),
        "n_variants_tested": len(results),
        "n_strategy_families": len(STRATEGY_REGISTRY),
        "leaderboard": leaderboard,
        "best_strategy": {
            "strategy": best["strategy"],
            "params": best["params"],
            "test": strip_curve(best["test"]),
            "full": strip_curve(best["full"]),
            "equity_curve": best_equity_curve,
        },
        "live_signal": live_signal,
        "walk_forward": {
            "log": wf_log,
            "summary": wf_summary,
        },
    }

    with open("../results/results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    print("Wrote results.json")
    print("Best strategy:", best["strategy"], best["params"])
    print("Live signal:", live_signal)


if __name__ == "__main__":
    main()
