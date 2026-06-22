# worldcup-predictor

Per-match probability predictions for the 2026 FIFA World Cup with daily live
re-forecasting, automated bet-slate generation, and a public dashboard.

**Philosophy — market-anchored ensemble.** Bookmaker consensus is hard to
beat over the long run, but blindly copying odds has no edge. We anchor on
de-vigged market consensus as a strong prior, then layer Dixon-Coles, ELO
priors, and contextual adjustments — and surface where the model *disagrees*
with the market as the interesting signal. Per-market walk-forward
validation gates every factor before it can carry stakes.

## What it does

- **Per match:** 1X2 + Asian Handicap + Over/Under + full scoreline distribution
- **Tournament:** Monte Carlo (≥50k runs) → group / round / title probabilities
- **Live:** daily refresh of odds, lineups, weather; realised RPS / Brier tracked
- **Bet slate:** `cli bet` drafts a Quarter-Kelly stake-sized recommendation
  list across AH + OU lines (default `--mode ahou`, mirroring mainstream
  Asian-book layout 输赢盘 / 让球盘 / 大小盘), with per-market walk-forward
  acceptance enforced

## 📖 Documentation

- **[`docs/guide.md`](docs/guide.md)** — full setup, daily workflow, CLI
  reference, model internals, Kelly discipline, paid-upgrade decisions, FAQ
- **[`CHANGELOG.md`](CHANGELOG.md)** — versioned behaviour changes
  (Keep a Changelog 1.1.0 / SemVer 2.0.0)
- **[`reports/backtests/FINDINGS.md`](reports/backtests/FINDINGS.md)** —
  every factor accepted or rejected, with backtest evidence
- **[`docs/competitor_analysis.md`](docs/competitor_analysis.md)** —
  9-project horizontal comparison anchoring the optimization backlog

## Quick start

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # see docs/guide.md §1 for the keys

PYTHONPATH=. python -m skill.helpers.cli fetch --all
PYTHONPATH=. python -m skill.helpers.cli predict --simulate
PYTHONPATH=. python -m skill.helpers.cli bet --bankroll 10000
```

See [`docs/guide.md`](docs/guide.md) for the full daily workflow, all CLI
subcommands, and how to interpret the bet slate.

## License

MIT. Methodology builds on the classic Dixon-Coles (1997) approach and the
open [`machina-sports/sports-skills`](https://github.com/machina-sports/sports-skills)
data toolkit.
