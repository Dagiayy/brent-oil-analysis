"""Deprecated location - kept as a thin re-export + CLI shim.

The implementation now lives in ``src.modeling.change_point_model``. This
module exists only so the original documented entry point
(``python src/change_point_model.py --data ... --output ...``) keeps working.
"""
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.modeling.change_point_model import (  # noqa: F401,E402
    ChangePointResult,
    compare_models,
    run_change_point_analysis,
    run_single_model,
)

if __name__ == "__main__":
    from src.modeling.change_point_model import ModelConfig, _parse_args

    args = _parse_args()
    config = ModelConfig(draws=args.draws, tune=args.tune, chains=args.chains, random_seed=args.seed)
    idata, change_date, summary = run_change_point_analysis(args.data, args.output, args.variant, config)
    print(f"Most probable change point date: {change_date.date() if change_date is not None else 'N/A'}")
    print(summary)
