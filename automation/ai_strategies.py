"""
Auto-growing pool of AI-invented trading strategies for XAU/USD.

Each entry in AI_STRATEGY_REGISTRY follows the same shape used by
STRATEGY_REGISTRY in engine_full.py:

    AI_STRATEGY_REGISTRY["Some Strategy Name"] = {
        "fn": some_function,      # (df, **params) -> pd.Series of -1/0/1, same index as df
        "grid": [ {param combo}, {param combo}, ... ],  # 2-6 combos
    }

The daily scheduled job invents and appends ONE new entry here per day (when
the pool has fewer than 60 entries), after smoke-testing the function.
automation/ai_strategies_meta.json tracks the date each entry was first
added -- a new AI strategy must be at least 30 days old before the engine
will let it become the live trading recommendation (see MATURATION_DAYS in
engine_full.py). This file is meant to be edited by the automation job, not
by hand -- but nothing bad happens if you read it or add entries yourself,
as long as you also add a matching entry to ai_strategies_meta.json.
"""
import numpy as np
import pandas as pd

AI_STRATEGY_REGISTRY = {}

# --- AI-invented strategies are appended below this line, one per day. ---
