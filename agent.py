"""Compatibility shim.

The live agent now lives in main.py, because that is the filename Kaggle
requires at the root of a submission. This module just re-exports it so the
existing tooling keeps working:

    python local_runner.py --agent agent.py --opponent starter --episodes 20
    python tournament.py

The previous crop-only "Melon Baron" v3 is still in git history if you want to
benchmark against it:

    git show HEAD~1:agent.py > v3_baseline.py
    python local_runner.py --agent main.py --opponent v3_baseline.py \\
        --episodes 30 --swap --seed 1

That head-to-head is the number that matters. v4 should win decisively; if it
does not, the tuning knobs are the TGT_* build targets in kagg_core.py, the
hire ceiling in kagg_market.py, and reserve_fraction() in kagg_plan.py.
"""

from main import agent  # noqa: F401

__all__ = ["agent"]
