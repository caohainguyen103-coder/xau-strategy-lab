import json

d = json.load(open("../results/results.json"))

# ---- seed for the page (embedded at publish time) ----
leaderboard_slim = []
for r in d["leaderboard"][:15]:
    leaderboard_slim.append({
        "strategy": r["strategy"],
        "params": r["params"],
        "score_test": r["score_test"],
        "test": r["test"],
        "full": r["full"],
    })

equity_curve = d["best_strategy"]["equity_curve"]
step = max(1, len(equity_curve) // 300)
equity_curve_thin = equity_curve[::step]
if equity_curve_thin[-1] != equity_curve[-1]:
    equity_curve_thin.append(equity_curve[-1])

page_seed = {
    "date": d["data_range"]["end"],
    "generated_at": d["generated_at"],
    "data_source": d["data_source"],
    "data_range": d["data_range"],
    "train_test_split_date": d["train_test_split_date"],
    "n_variants_tested": d["n_variants_tested"],
    "n_strategy_families": d["n_strategy_families"],
    "leaderboard": leaderboard_slim,
    "best_strategy": {
        "strategy": d["best_strategy"]["strategy"],
        "params": d["best_strategy"]["params"],
        "test": d["best_strategy"]["test"],
        "full": d["best_strategy"]["full"],
        "equity_curve": equity_curve_thin,
    },
    "live_signal": d["live_signal"],
    "walk_forward": d["walk_forward"],
}

with open("../results/seed_page.json", "w") as f:
    json.dump(page_seed, f, indent=2)

# ---- seed for db: runs/{date} ----
runs_doc = dict(page_seed)
runs_doc["date"] = d["data_range"]["end"]
with open("../results/seed_runs_doc.json", "w") as f:
    json.dump(runs_doc, f, indent=2)

# ---- seed for db: signals/{date} ----
sig = d["live_signal"]
signals_doc = {
    "date": sig["as_of_date"],
    "strategy": d["best_strategy"]["strategy"],
    "params": d["best_strategy"]["params"],
    "position": sig["position"],
    "label": sig["label"],
    "as_of_close": sig["as_of_close"],
}
with open("../results/seed_signal_doc.json", "w") as f:
    json.dump(signals_doc, f, indent=2)

print("page_seed bytes:", len(json.dumps(page_seed)))
print("runs_doc bytes:", len(json.dumps(runs_doc)))
print("signal_doc bytes:", len(json.dumps(signals_doc)))
print(signals_doc)
