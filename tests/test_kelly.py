"""Tests for `skill.bet.kelly`."""
from __future__ import annotations

from skill.bet.kelly import (
    Opportunity, kelly_fraction, edge, portfolio_kelly, is_whitelisted,
    DEFAULT_KELLY_FRACTION, DEFAULT_MAX_PER_BET,
)


def _approx(a, b, tol=1e-6):
    assert abs(a - b) < tol, f"{a} vs {b}"


def test_no_edge_no_bet():
    """50% prob @ 2.0 odds = exact fair → Kelly fraction must be 0."""
    assert kelly_fraction(0.5, 2.0) == 0.0


def test_full_kelly_formula():
    """Reference: p=0.6, odds=2.0 → b=1, full Kelly = (1·0.6 − 0.4)/1 = 0.2."""
    _approx(kelly_fraction(0.6, 2.0, fraction=1.0), 0.2)
    _approx(kelly_fraction(0.6, 2.0, fraction=0.25), 0.05)


def test_negative_edge_returns_zero():
    """If we'd lose money long-term, Kelly says don't bet."""
    assert kelly_fraction(0.4, 2.0) == 0.0


def test_edge_calculation():
    _approx(edge(0.55, 2.0), 0.05)
    _approx(edge(0.5, 2.0), 0.0)


def test_portfolio_drops_below_threshold():
    """edge below threshold should be filtered out; pass explicit threshold for stability."""
    ops = [
        Opportunity("low edge", p_win=0.51, decimal_odds=2.0),  # edge = 1%
        Opportunity("good edge", p_win=0.55, decimal_odds=2.0),  # edge = 5%
    ]
    out = portfolio_kelly(ops, bankroll=10000, edge_threshold=0.03)
    labels = [r["label"] for r in out]
    assert "low edge" not in labels
    assert "good edge" in labels


def test_portfolio_per_bet_cap():
    """A 50%-edge bet at quarter Kelly would be ~12.5%, but the cap is 5%."""
    ops = [Opportunity("huge edge", p_win=0.95, decimal_odds=2.0)]
    out = portfolio_kelly(ops, bankroll=10000)
    assert out[0]["kelly_fraction"] <= DEFAULT_MAX_PER_BET + 1e-9


def test_portfolio_total_cap():
    """Many uncapped 5% bets should be scaled to total ≤ 30%."""
    ops = [Opportunity(f"bet {i}", p_win=0.7, decimal_odds=2.0) for i in range(10)]
    out = portfolio_kelly(ops, bankroll=10000)
    total = sum(r["kelly_fraction"] for r in out)
    assert total <= 0.30 + 1e-6


def test_default_quarter_kelly():
    """Sanity: default fraction is quarter Kelly."""
    assert DEFAULT_KELLY_FRACTION == 0.25


def test_whitelist_rejects_ou15():
    """FINDINGS Run 27: OU 1.5 was anti-skill in walk-forward, must fail closed."""
    assert is_whitelisted("ou_1.5") is False
    assert is_whitelisted("ah_minus_0.5") is True
    assert is_whitelisted("1x2") is True
    assert is_whitelisted("unknown_market") is False


def test_portfolio_drops_rejected_market():
    """Even an enormous-edge bet on a rejected market must be silently dropped."""
    ops = [
        Opportunity("OU 1.5 win", p_win=0.99, decimal_odds=2.0, market="ou_1.5"),
        Opportunity("AH -0.5 win", p_win=0.6, decimal_odds=2.0, market="ah_minus_0.5"),
    ]
    out = portfolio_kelly(ops, bankroll=10000)
    labels = [r["label"] for r in out]
    assert "OU 1.5 win" not in labels
    assert "AH -0.5 win" in labels


if __name__ == "__main__":
    import inspect
    failures = 0
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and inspect.isfunction(f)]
    for name, fn in fns:
        try:
            fn()
            print(f"  ok  {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {name}: {e}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    raise SystemExit(failures)
