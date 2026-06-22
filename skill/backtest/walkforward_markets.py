"""Walk-forward backtest for derived AH / OU markets.

P0.2a (`derived_markets.py`) integrates the DC score grid into Asian Handicap
and Over/Under probabilities. P1.3 verifies those probabilities are well
calibrated on held-out matches — without this evidence we cannot trust
`cli bet` to size AH/OU stakes once the live odds feed lands (P0.2b).

Without a historical bookmaker archive we cannot compute realised ROI here;
that comes when The Odds API Business is purchased. What we *can* do
walk-forward today:

  * Brier score and log-loss on each AH/OU line vs the actual outcome
    (margin / total goals from the historical scoreline).
  * Reliability buckets and Expected Calibration Error (ECE) — the standard
    Constantinou-Fenton style check the rest of this project uses.
  * A constant-rate baseline (the empirical pre-test base rate) to confirm
    the model adds information beyond a no-skill prior.

The same look-ahead-free guards as `walkforward.py` apply: ELO from
`compute_elo_history` is pre-match by construction, DC is refit only on
matches strictly before each test date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..model import derived_markets as derived
from ..model import dixon_coles as dc
from ..model.elo import compute_elo_history
from .walkforward import MAJOR


# Standard test lines — half lines for clean binary calibration; integer lines included
# for P3.4 validation of the expanded MARKET_WHITELIST.
AH_LINES = (-2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
OU_LINES = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)


def _ah_outcome(margin: int, line: float) -> int | None:
    """AH settlement: 1=home covers, 0=away covers, None=push (integer line, exact margin).

    Push occurs only on integer lines when margin == -line exactly.
    """
    adjusted = margin + line   # positive → home wins
    if adjusted == 0:
        return None  # push
    return 1 if adjusted > 0 else 0


def _ou_outcome(total: int, line: float) -> int | None:
    """OU settlement: 1=over, 0=under, None=push (integer line, total == line)."""
    if total == line:
        return None  # push
    return 1 if total > line else 0


def _bucket_ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error: Σ (n_b/N) · |mean_p − mean_y| over equal-width bins."""
    if len(probs) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        if not mask.any():
            continue
        ece += mask.sum() / len(probs) * abs(probs[mask].mean() - outcomes[mask].mean())
    return float(ece)


def _market_metrics(probs: np.ndarray, outcomes: np.ndarray) -> dict:
    """Standard binary scoring + calibration."""
    if len(probs) == 0:
        return {}
    p = np.clip(probs, 1e-9, 1 - 1e-9)
    y = outcomes.astype(float)
    return {
        "n": int(len(p)),
        "base_rate": round(float(y.mean()), 4),
        "mean_pred": round(float(p.mean()), 4),
        "brier": round(float(np.mean((p - y) ** 2)), 5),
        "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
        "ece": round(_bucket_ece(p, y), 5),
        "top_pick_accuracy": round(float(np.mean((p > 0.5) == (y > 0.5))), 4),
    }


def _baseline_metrics(outcomes: np.ndarray, base_rate: float) -> dict:
    """No-skill baseline: predict the (look-ahead-free) empirical base rate every time."""
    n = len(outcomes)
    if n == 0:
        return {}
    p = np.full(n, base_rate, dtype=float)
    return _market_metrics(p, outcomes)


def run(
    results: pd.DataFrame,
    start: str,
    end: str,
    refit_days: int = 60,
    majors_only: bool = True,
    xi: float = 0.0010,
    train_years: float = 3.0,
    ah_lines: tuple[float, ...] = AH_LINES,
    ou_lines: tuple[float, ...] = OU_LINES,
    verbose: bool = True,
) -> dict:
    hist, _ = compute_elo_history(results)
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    test = hist[(hist["date"] >= t0) & (hist["date"] <= t1)].copy()
    if majors_only:
        test = test[test["tournament"].isin(MAJOR)]
    test = test.dropna(subset=["home_score", "away_score"]).sort_values("date")
    if test.empty:
        return {"error": "no test matches in window"}

    # Look-ahead-free base rate: empirical hit rate on non-push matches BEFORE the test window.
    train_pool = hist[hist["date"] < t0].dropna(subset=["home_score", "away_score"])
    train_margins = (train_pool["home_score"] - train_pool["away_score"]).astype(int).to_numpy()
    train_totals = (train_pool["home_score"] + train_pool["away_score"]).astype(int).to_numpy()
    # For integer lines, push matches are excluded from base rate (same as binary metrics).
    def _base_ah(ln):
        mask = (train_margins + ln) != 0  # non-push
        return float((train_margins[mask] > -ln).mean()) if mask.sum() > 0 else 0.5
    def _base_ou(ln):
        mask = train_totals != ln  # non-push
        return float((train_totals[mask] > ln).mean()) if mask.sum() > 0 else 0.5
    base_ah = {ln: _base_ah(ln) for ln in ah_lines}
    base_ou = {ln: _base_ou(ln) for ln in ou_lines}

    # Per-line accumulators
    ah_probs = {ln: [] for ln in ah_lines}
    ah_outs = {ln: [] for ln in ah_lines}
    ou_probs = {ln: [] for ln in ou_lines}
    ou_outs = {ln: [] for ln in ou_lines}

    model = None
    model_asof = None
    skipped = 0

    for r in test.itertuples(index=False):
        as_of = r.date
        if model is None or (as_of - model_asof).days >= refit_days:
            try:
                model = dc.fit(results, as_of=as_of, xi=xi, train_years=train_years)
                model_asof = as_of
            except ValueError:
                skipped += 1
                continue

        if r.home_team not in model.attack or r.away_team not in model.attack:
            skipped += 1
            continue

        lam_h, lam_a = model.lambdas(r.home_team, r.away_team, neutral=bool(r.neutral))
        margin = int(r.home_score) - int(r.away_score)
        total = int(r.home_score) + int(r.away_score)

        for ln in ah_lines:
            res = derived.asian_handicap(lam_h, lam_a, model.rho, ln)
            outcome = _ah_outcome(margin, ln)
            if outcome is not None:  # skip push (integer line, exact margin)
                ah_probs[ln].append(res["p_home"])
                ah_outs[ln].append(outcome)
        for ln in ou_lines:
            res = derived.over_under(lam_h, lam_a, model.rho, ln)
            outcome = _ou_outcome(total, ln)
            if outcome is not None:  # skip push
                ou_probs[ln].append(res["p_over"])
                ou_outs[ln].append(outcome)

    ah_report, ou_report = {}, {}
    for ln in ah_lines:
        p, y = np.array(ah_probs[ln]), np.array(ah_outs[ln])
        ah_report[f"AH_{ln:+.1f}"] = {
            "model": _market_metrics(p, y),
            "baseline_constant": _baseline_metrics(y, base_ah[ln]),
        }
    for ln in ou_lines:
        p, y = np.array(ou_probs[ln]), np.array(ou_outs[ln])
        ou_report[f"OU_{ln:.1f}"] = {
            "model": _market_metrics(p, y),
            "baseline_constant": _baseline_metrics(y, base_ou[ln]),
        }

    out = {
        "window": [start, end],
        "majors_only": majors_only,
        "xi": xi,
        "refit_days": refit_days,
        "train_years": train_years,
        "skipped": skipped,
        "n_matches": int(len(test) - skipped),
        "asian_handicap": ah_report,
        "over_under": ou_report,
        "note": (
            "ROI not computed — requires historical bookmaker AH/OU odds "
            "(deferred until P0.2b / The Odds API Business). Calibration check only."
        ),
    }
    if verbose:
        import json
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return out
