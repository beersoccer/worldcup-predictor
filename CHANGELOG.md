# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/).

Categories used: `Added` · `Changed` · `Deprecated` · `Removed` · `Fixed` · `Security` · `Backtest`.
Doctrine: a `Backtest` entry is required whenever a prediction factor is added,
removed, or has its weight changed (cross-references `reports/backtests/FINDINGS.md`).

---

## [Unreleased]

### Added
- **`predict --date YYYY-MM-DD`**. Writes predictions to `reports/<date>/`
  using that date as the DC model `as_of` cutoff and lineup lookup target.
  Allows users in non-UTC timezones to pre-generate next-day slates the
  evening before without waiting until local midnight.
- **ClubElo three-tier resilience** (`data_loader.fetch_club_elo`).
  Primary: `api.clubelo.com` (live daily snapshot, 7-day local cache TTL).
  Fallback: `xgabora/Club-Football-Match-Data-2000-2025` GitHub mirror
  (bi-monthly snapshots, 895 clubs, latest 2025-06-01) — activated
  automatically when the primary API returns 5xx / times out.
  Last resort: stale local cache of any age.
  Resolves the `[talent skipped] 503` that appeared when `api.clubelo.com`'s
  Windows IIS server was down during WC2026.

### Fixed
- **`bet --date` now filters to that date's matches only**. Previously all
  72 fixtures in `predictions.json` were scored regardless of match date,
  producing 120+ spurious recommendations spanning the full tournament.

### Added
- **1X2 → λ_market inversion** (`derived_markets.infer_market_lambdas`).
  Industry-standard path used by Pinnacle / academic references for
  converting European 1X2 odds to Asian Handicap and Over/Under fair prices:
  hold DC's ρ fixed and solve via L-BFGS-B for (λ_h^M, λ_a^M) that reproduces
  the de-vigged 1X2 exactly through the DC score grid. Pricing AH/OU off
  those market λ stays internally consistent across all lines — no longer
  limited to the ±0.5 half lines reachable by direct 3-bucket mapping.
- **`cli bet --mode ahou`** (new default). Generates 3 dynamically-selected
  AH lines (centred on `round-to-half(-(λ_h - λ_a))`) AND 3 OU lines
  (centred on `round-to-half(λ_h + λ_a)`) per match — matching the layout
  of mainstream Asian books (输赢盘/让球盘/大小盘 三栏式). New mode choices:
  `ah`, `ou`, `ahou` (default), `1x2`, `all`.
- **OU recommendations** are now first-class. `_ou_opportunities()` mirrors
  `_ah_opportunities()` via the same λ-inference path. OU 1.5 remains
  hard-blocked (Run 27 reverse-skill finding).
- **AH integer + OU integer/half settlement** in `_betting_payload`.
  Push-bearing lines (AH 0 / ±1 / ±2 and OU 2 / 3 / 4) refund stake on
  exact-margin results. 7 new tests (AH 0 push, AH -1 push at margin=1,
  OU 2.5 over/under, OU 3 push, unknown-market skip) added.
- **9 new tests in `tests/test_market_lambda_inference.py`** verifying
  inversion recovers DC λ when the 1X2 came from DC, handles ρ ≠ 0,
  rejects degenerate inputs, and works on low-scoring matches.

### Changed
- **Default `cli bet` mode is now `ahou`** (was `ah` with only ±0.5).
  AH still single-mode via `--mode ah`; OU alone via `--mode ou`.
- **Whitelist expanded** (`MARKET_WHITELIST` in `kelly.py`): AH ±2.5,
  AH integers 0/±1/±2, OU 2/3/4/4.5 added. Lines beyond the Run 27
  walk-forward sample are flagged `# backtest pending (P3.4)` — accepted
  on the strength of the λ-inference consistency, but a per-line
  walk-forward must be run before the next major release.
- `_predict_one` now writes `rho` to each prediction record (previously
  only `lambda_home` / `lambda_away` were exposed).

### Added
- **Dashboard betting panel** (`site/index.html`, `cli publish`). Today's bet
  slate is surfaced with its Kelly stake, edge, and odds; cumulative P&L,
  ROI, and max drawdown are computed by reconciling each settled bet against
  the actual match result. Empty-slate, zero-history, and partial-settlement
  cases all render gracefully — no live tournament data required. Bilingual
  (EN / 中文) labels follow the existing i18n pattern. (P2.1)
- 7 new unit tests in `tests/test_betting_payload.py` covering empty-state,
  winning settlement, losing settlement, max-drawdown tracking, unsettled
  matches, and AH/OU bets being skipped until P0.2b lands.

### Fixed
- **Penalty-shootout coin is now fair (50/50)**, not strength-weighted by
  90-minute λ. Walk-forward on 231 actual post-2010 shootouts shows the
  prior `lam/(lam+mu)` formulation was *anti-skill* (Brier 0.2683 vs coin's
  0.2500, accuracy 0.489 vs 0.506) — see Run 29. Effect on tournament odds
  is modest (shootouts are rare and roughly balanced) but every simulated
  knockout tie was previously biased without evidence.

### Investigated, not adopted
- **Bayesian shootout skill prior** (P1.2 hypothesis from competitor
  `dexorynlabs`). Walk-forward on n=339 historical shootouts: every tested
  shrinkage strength α∈{0.5..50} is worse than a coin on Brier, raw win
  rate is worst of all (Brier 0.2936). No team-level shootout skill is
  recoverable from the available sample. (Run 29)

### Added
- **Cross-confederation strength gap factor** (`skill/model/confederations.py`,
  `data/confederations.json`). The DC fit, calibrated mostly on intra-confed
  matches, systematically under-prices the strength gap when UEFA / CONMEBOL
  meet other confederations; a symmetric ±0.075 log-lambda shift corrects it.
  Wired into `context.py` and surfaced as a per-fixture note. (P1.1, Run 28)
- 9 new unit tests in `tests/test_confederations.py` covering country lookup,
  alias coverage, the strong-vs-weak adjustment, and same-confed no-op behaviour.

### Backtest
- **Run 28** (FINDINGS.md) — cross-confederation gap on majors 2010-2024
  (n=212 cross-confed matches). Monotonically better at every tested gap
  (0.05 → 0.30), peak Δ −0.00234 at gap=0.20-0.22. Adopted gap=0.15 (inside
  tested-good range, conservative against single-sample peak overfitting,
  matching Run 12's discipline). Magnitude is 1-2 orders larger than the
  rest factor and same band as talent / FC25 / 3-year window.

---

## [0.1.0] — 2026-06-19

First versioned release: pivot from descriptive 1X2 forecasts to stake-ready
Asian Handicap / Over-Under bet slates. Merged in PR #1
(`feat/asian-handicap-kelly`).

### Added
- **Walk-forward AH/OU calibration backtest** (`skill/backtest/walkforward_markets.py`)
  with `cli backtest --markets`. Tests Brier / log-loss / ECE per line vs a
  no-skill base-rate baseline. (P1.3)
- **Per-market acceptance whitelist** in `skill/bet/kelly.py`. Markets that
  fail walk-forward calibration cannot be bet on, regardless of any individual
  edge — same anti-curve-fitting rule as Runs 14/16/17.
- **Asian Handicap & Over/Under fair-price derivation** (`skill/model/derived_markets.py`).
  Integrates the existing Dixon-Coles score grid into AH/OU probabilities and
  EV-zero fair odds. Supports integer / half / quarter lines with push handling.
  Cross-validated against the Skellam (margin) and Poisson (total) closed forms
  at `rho=0`. (P0.1 + P0.2a)
- **Kelly portfolio engine** (`skill/bet/kelly.py`). Quarter-Kelly default with
  the discipline locked in `.claude/plans/optimization_backlog.md §9`:
  per-bet cap 5%, portfolio cap 30%, edge gate 3%, signal floor 0.5%. (P0.3)
- **`cli bet` subcommand**. Reads the latest predictions, drafts a stake-sized
  slate against the live per-match 1X2 market, and logs each slate to
  `reports/bets/<date>.json` for later settlement by `cli review`.
- `tests/` directory with 26 unit tests covering AH/OU derivation, Kelly
  discipline, and walk-forward market metrics (`PYTHONPATH=. python tests/test_*.py`).
- `docs/competitor_analysis.md` — horizontal review of 9 GitHub
  worldcup-predictor projects, anchoring the optimization backlog.

### Changed
- `_predict_one` now attaches `derived` (the full AH/OU ladder) to every
  fixture's prediction record. Existing fields are unchanged.

### Backtest
- **Run 27** (FINDINGS.md) — derived AH/OU calibration on majors 2018-2024
  (n=574). All four Asian Handicap lines (-1.5, -0.5, +0.5, +1.5) beat the
  no-skill baseline on Brier by 0.020-0.049 with comparable ECE; **AH ADOPTED**
  for `cli bet`. Over/Under is marginal: OU 1.5 is *anti-skill* (Brier 0.005
  worse than baseline) and **REJECTED**; OU 2.5 / OU 3.5 are accepted with
  low-confidence flags. Whitelist enforces the decision in code.

### Deferred
- **Live Pinnacle AH/OU feed** (P0.2b). Pinnacle's official API was closed to
  the public in 2025-07; The Odds API ($30/mo) is the only compliant relay
  and will be onboarded for the European league season, not for the World Cup.
  Until then `cli bet` only acts on 1X2 markets (Polymarket / Kalshi); AH/OU
  bets are intentionally suppressed to avoid self-arbitrage against the
  model's own fair price.

---

## Conventions for future releases

- **Versioning**: bump `MAJOR.MINOR.PATCH` on tagged releases.
  - `MAJOR` — incompatible CLI / report-schema change
  - `MINOR` — new prediction factor, new market, new CLI subcommand
  - `PATCH` — bug fix, doc update, dependency bump with no behaviour change
- **Tag format**: `vX.Y.Z` (annotated tag). Pre-tournament and end-of-tournament
  snapshots get tagged so live results stay reproducible.
- **A release entry must answer three questions**:
  1. What changed (Added / Changed / Fixed)?
  2. Did any factor enter or leave the model? (Backtest entry, with `Run NN`
     reference to FINDINGS.md.)
  3. Is the dashboard schema (`site/data.json` keys) backwards-compatible?
- **Unreleased changes accumulate at the top** under `## [Unreleased]`. On
  release, the section is renamed to `## [vX.Y.Z] — YYYY-MM-DD` and a new
  empty `[Unreleased]` is created.
