# Open-Source Football Prediction Projects: Deep Technical Analysis

> Research date: 2026-07-13  
> Projects analyzed: 5 | Source files reviewed: 40+

---

## Executive Summary

1. **penaltyblog** is the most reusable library: broadest model zoo (7 goal models), 7 de-vigging methods, full Kelly + backtest framework, and Cython-optimized. Competition-agnostic by design. Best single source for borrowable primitives.
2. **AIrsenal** has the most sophisticated Bayesian treatment and the cleanest temporal-decay implementation (exponential ε-weighting in `bpl_next`), but is deeply FPL-coupled and not reusable without surgery.
3. **ProphitBet** is the only project with a clean ML ensemble abstraction (9 classifiers behind a unified interface), Boruta feature selection, and isotonic probability calibration — none of which appear in the other four projects.
4. **Club_Soccer_Season_Projections** is the only project with multi-competition Monte Carlo (8 leagues + UCL) and xG→ELO conversion, but has zero time-decay and scrapes Wikipedia — not production quality.
5. **FootballBettingModel** is the thinnest project (mostly a Jupyter notebook), but uniquely integrates FIFA player ratings as match features — a novel cross-domain feature source.

---

## 1. penaltyblog (martineastwood/penaltyblog)

### Architecture

A **Python library** (not an application) providing composable primitives for football analytics. Structured into 12 subpackages:

| Subpackage | Purpose |
|-----------|---------|
| `models` | 7 goal models (see below) |
| `implied` | 7 de-vigging methods |
| `betting` | Kelly criterion, arbitrage, value bets |
| `backtest` | Walk-forward backtesting engine |
| `metrics` | RPS, Brier, Ignorance score |
| `ratings` | ELO, Pi, Massey, Colley |
| `bayes` | MCMC ensemble sampler |
| `matchflow` | Lazy-loading data pipeline |
| `scrapers` | Data collection |
| `fpl` | Fantasy Premier League utilities |
| `xt` | Expected threat |
| `viz` | Visualization |

### Prediction Models

| Model | Key Features |
|-------|-------------|
| `PoissonGoalsModel` | Basic Poisson, attack/defense/HFA params, optional weights |
| `DixonColesModel` | + rho low-score correction, Cython-optimized gradient |
| `BivariatePoisson` | Joint Poisson, captures score correlation |
| `BayesianGoalModel` | DC log-likelihood + ensemble MCMC, 4 chains × 2000 samples |
| `HierarchicalBayesianGoalModel` | Learns league-wide σ_attack / σ_defense automatically |
| `NegativeBinomial` | Overdispersed count model |
| `ZeroInflatedPoisson` | Models excess draws/0-0 |
| `WeibullCopulaModel` | Continuous marginals + copula for tail/dependency modeling |

All models take `weights` parameter — time decay is **external, precomputed** (not built into models).

### Data Pipeline

`MatchFlow` is a lazy-loading streaming pipeline (JSON, StatsBomb API, Opta API). Supports filter/select/flatten/join/group/summarize. Competition-agnostic — data format is standardized internally.

### Betting / Kelly

`kelly.py` implements:
- Standard Kelly: `f* = edge / (odds - 1)`
- Fractional Kelly via `fraction` parameter  
- `multiple_kelly_criterion()`: two modes — (1) independent bets scaled proportionally, (2) scipy portfolio optimization maximizing log growth across mutually exclusive outcomes

`implied.py` implements 7 de-vigging methods: multiplicative, additive, power, Shin (1992), differential margin weighting (Buchdahl), odds ratio, logarithmic. All use numerical root-finding where needed.

### Backtesting

Walk-forward engine with daily retraining:
- `lookback = df[df["date"] < date]` / `test = df[df["date"] == date]`
- Account class tracks bankroll history, max/min, ROI
- `stop_at_negative` flag for risk management
- Metrics: win%, ROI, profit, bankroll trajectory

### Competition Abstraction

**Fully league-agnostic.** All models accept team name strings; no competition-specific logic. MatchFlow pipeline normalizes data format regardless of source.

### Time Decay

Not built into models. Caller precomputes weights (e.g., exponential decay) and passes via `weights=` parameter. Dixon-Coles `xi` must be computed externally.

### Evaluation

RPS array + average, multiclass Brier score, ignorance (log loss). All in `metrics` subpackage.

### Code Quality

Production-grade: Cython hot paths, mypy type stubs (`.pyi`), pre-commit hooks, pytest, ReadTheDocs, >195 stars. Well-maintained.

---

## 2. AIrsenal (alan-turing-institute/AIrsenal)

### Architecture

An **end-to-end FPL application** (not a library). Two-tier prediction system:

1. **Team model** (`bpl_interface.py`): `ExtendedDixonColesMatchPredictor` from `bpl-next` (Bayesian, wraps pymc-style MCMC). Fits on 3 seasons of history.
2. **Player model** (`player_model.py`): Dirichlet-Multinomial conjugate Bayes. Predicts P(score), P(assist), P(neither) per player per goal scored.
3. **FPL optimizer** (`optimization_squad.py`, `optimization_transfers.py`): Integer programming for squad/transfer selection.

### Data Pipeline

SQLAlchemy ORM with SQLite. Tables: Player, PlayerAttributes, Fixture, Result, PlayerScore, Team, FifaTeamRating, Absence, Transaction. Data sourced from FPL official API. Schema is highly FPL-specific (gameweeks, price, captain, bench, chips).

### Temporal Decay

**Best implementation of the five projects.** In `bpl_interface.py`:
```python
DEFAULT_TEAM_EPSILON = 0.9  # calibrated across 20/21–24/25 seasons
weights = exp(-epsilon * time_diff)
```
Player model uses `weights = exp(-0.2 * time_diff)`. `rescale_weights=True` normalizes so old matches don't reduce effective sample size.

### Prediction → FPL Points

`prediction_utils.py`: for each fixture, generates P(home scores k goals) and P(away scores k goals) for k=0..10. Multinomial partitioning assigns goals to players. FPL position rules applied (GK clean sheet = 6pts, etc.). Minutes played modulates participation probability.

### FIFA Ratings Integration

Team covariates: `[att, mid, defn, ovr]` ratings per season from `FifaTeamRating` table. Used to initialize newly promoted teams with no match history.

### Neutral Venue

`NeutralDixonColesMatchPredictor` variant used for neutral venue games. In training: `neutral_venue = np.zeros(len(results))`.

### Competition Abstraction

**Hardcoded to EPL/FPL.** Gameweek structure (38 rounds), FPL team IDs, position rules, and optimization constraints are all EPL-specific. Adapting to other competitions requires major refactoring.

### Evaluation

No explicit RPS/Brier evaluation framework. Model quality assessed implicitly through FPL points return. Epsilon=0.9 was empirically optimized.

### Code Quality

Good: 2347 commits, Docker support, uv-based dependency management, pre-commit hooks, pytest. 96.8% Jupyter Notebook by file size (analysis notebooks). Core framework is clean Python.

---

## 3. ProphitBet (kochlisGit/ProphitBet-Soccer-Bets-Predictor)

### Architecture

A **desktop GUI application** (Tkinter) wrapping an ML ensemble. Key layers:

```
GUI (src/gui/) → Model Layer (src/models/) → Preprocessing (src/preprocessing/)
                              ↑
               9 classifiers behind ClassificationModel ABC
```

### ML Models

All classifiers implement `build_classifier() → BaseEstimator`. Unified via `ClassificationModel` ABC:

| Classifier | File |
|-----------|------|
| Logistic Regression | `logistic.py` |
| LDA/QDA | `discriminant.py` |
| Decision Tree | `decisiontree.py` |
| Random Forest | `randomforest.py` |
| XGBoost | `extremeboosting.py` |
| KNN | `knn.py` |
| Naive Bayes | `naivebayes.py` |
| SVM | `svm.py` |
| Deep Neural Net | `neuralnets/` |

Probability calibration: optional `CalibratedClassifierCV(method='isotonic')` wraps any classifier.

### Feature Engineering

`StatisticsEngine` (`src/preprocessing/statistics.py`) computes per-team rolling features over configurable window N:

**24 basic features:**
- HW, AW, HL, AL (win/loss counts)
- HGF, AGF, HAGF (goals forward)
- HGA, AGA (goals against)
- HGD, AGD, HAGD (goal differential)
- HWGD, AWGD, HLGD, ALGD (margin wins/losses > threshold)
- HW%, HL%, AW%, AL% (cumulative rates from season start)

**4 extended features:**
- HSTF, ASTF (shots on target)
- HCF, ACF (corners)

Data leakage prevention: `.shift(1).rolling(N).sum()` excludes current match.

Feature selection: Boruta algorithm (wrapper around RandomForest) + correlation analysis + variance filtering.

### Data Sources

- Historical: football-data.co.uk
- Upcoming fixtures: footystats.org

### Competition Abstraction

Semi-configurable. Leagues stored via `src/database/league.py`. GUI allows selecting different leagues. No hardcoded league-specific rules visible.

### Betting Integration

Threshold filtering on predicted probability and odds ranges. "Profit Balance" metric for strategy evaluation. No explicit Kelly criterion implementation.

### Evaluation

StratifiedKFold (k-fold, shuffle=True) + temporal sliding window validation. Metrics: Accuracy, F1 (macro), Precision (macro), Recall (macro). No RPS/Brier.

### Time Decay

None. All historical matches in the rolling window weighted equally.

### Code Quality

Medium. GUI-centric architecture couples UI to model logic. No tests visible. Well-documented README. Active community (desktop app users).

---

## 4. Club_Soccer_Season_Projections (salikfaisal/Club_Soccer_Season_Projections)

### Architecture

A **research script** (not a library or app). Main file: `Club_Soccer_Season_Projections.py` orchestrates the simulation; five helper modules.

### Prediction Model

Three-component composite ELO:

| Component | Weight | Source |
|----------|--------|--------|
| Club ELO (match outcomes) | 50% | clubelo.com API |
| xG-adjusted ELO | 25% | fbref.com (Opta) |
| Squad quality ELO | 25% | footballtransfers.com |

### ELO Update Formula

K=20 base, scaled by `sqrt(abs(goal_difference))`. Home field advantage: starts at 50 ELO points per country, updates as `hfa += 0.075 * delta_elo`. Neutral venues: HFA zeroed for UCL dates.

### xG → ELO Conversion (`xg_to_elo.py`)

1. Win expectancy from ELO differential (standard formula)
2. Expected goal margin: `NormalDist(0, 1.3).inv_cdf(win_prob)` → maps strength to margin
3. Poisson probability matrix (0–10 goals) from xG values
4. ELO exchange weighted by `sqrt(goal_diff)` per Poisson outcome

This is a **novel composite**: ELO updated proportionally to Poisson-probability-weighted goal difference outcomes, not just match result.

### Goal Probability Model (`Goal_Probabilities.py`)

Uses **normal distribution** (not Poisson) for goal margin: `NormalDist(0, 1.3)`. Total goals drawn from empirical distribution of 1,826 European top-league matches. Gives 35/30/35 W/D/L split for equal teams.

### Monte Carlo Simulation

10,000 iterations per competition. Per iteration:
- Deep-copy current standings
- For each unplayed fixture (`"TBD"` marker): call `gp.match_result(home_elo, away_elo)`
- Update standings
- Record outcomes

### Competition Coverage

8 competitions: Champions League, PL, La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga. UCL handled as separate knockout simulation class with group stage + playoffs + R16 + QF + SF + Final.

### Data Pipeline

Web scraping only:
- Wikipedia (current season results/fixtures via BeautifulSoup)
- clubelo.com API (ELO ratings, HFA values)
- fbref.com (xG metrics)
- footballtransfers.com (squad valuations)

No persistent database. Results exported to CSV.

### Competition Abstraction

Reasonably multi-competition. League tiebreakers vary by country (head-to-head for Italy/Spain/Portugal implemented separately). UCL knockout format fully modeled.

### Time Decay

**None.** All historical ELO equally weighted.

### Evaluation

None. No backtesting, no probabilistic scoring. Output is directly the projected standings/probabilities.

### Code Quality

Research/personal project quality. No tests, no packaging, no type hints. Clear and readable but not production-ready.

---

## 5. FootballBettingModel (qwyt/FootballBettingModel)

### Architecture

Primarily a **Jupyter notebook** (`241.ipynb`, 93.8% of codebase). Supporting utilities in `workbench/src/`:

| File | Purpose |
|------|---------|
| `model_config.py` | XGBoost/RF/LR hyperparameters |
| `data_loader.py` | Load from Kaggle "Ultimate 25k+ Matches" DB |
| `data_process.py` | Rolling feature construction, temporal alignment |
| `graph.py` | EDA visualization |

### Prediction Models

Three evaluated:
1. **XGBoost** — best probability calibration, selected for final strategy
2. **Random Forest** — middle ground
3. **Logistic Regression** — poor probability calibration, underpredicts extremes

### Feature Engineering

- Rolling weighted/unweighted statistics: match results, goals scored/conceded, points per game
- **FIFA player ratings** aggregated at team level per match date — unique cross-domain feature
- Home/away split features
- Temporal alignment: FIFA ratings joined to match data by season

The FIFA ratings feature is architecturally novel: it adds a roster-quality signal independent of recent form, capturing squad composition changes (transfers, injuries) that ELO-based methods miss.

### Kelly Criterion

Applied post-prediction:
- Model outputs probability estimates P(H), P(D), P(A)
- Kelly fraction computed against bookmaker odds
- Reported 5.5% ROI over 75 games (small sample, caution warranted)

### Data Source

Kaggle "Ultimate 25k+ Matches Football Database" — covers 7+ European leagues with integrated betting odds from multiple bookmakers.

### Competition Abstraction

Multi-league by default (the Kaggle DB covers EPL, La Liga, Serie A, Bundesliga, Ligue 1, etc.). No league-specific logic visible.

### Time Decay

Weighted rolling statistics (recency-weighted window) used as features. No decay in model training itself.

### Evaluation

- Probability calibration plots
- Confidence threshold filtering (only bet when max(P) > threshold)
- No explicit RPS/Brier
- Walk-forward implied but not rigorously implemented (notebook structure)

### Code Quality

Low. Mostly exploratory notebook. Limited reusability without refactoring. Small test set (75 games).

---

## Feature Comparison Matrix

| Dimension | penaltyblog | AIrsenal | ProphitBet | Club_Soccer_Proj | FootballBettingModel |
|-----------|------------|----------|------------|-----------------|---------------------|
| **Core model paradigm** | Statistical (Poisson/DC/Bayes) | Bayesian DC | ML ensemble (9 classifiers) | ELO + Monte Carlo | ML (XGBoost/RF/LR) |
| **Model count** | 8 goal models | 2 DC variants | 9 classifiers | 1 composite ELO | 3 |
| **Bayesian MCMC** | Yes (custom ensemble sampler) | Yes (bpl-next, NUTS) | No | No | No |
| **Hierarchical priors** | Yes (league σ learning) | No | No | No | No |
| **Time decay** | External weights (any function) | exp(−ε·t), ε=0.9 | None | None | Rolling window features |
| **xG integration** | No | No | Shots on target (proxy) | Yes (ELO adjustment) | No |
| **Player-level model** | No | Yes (Dirichlet-Multinomial) | No | Squad quality (aggregate) | Yes (FIFA ratings) |
| **Home/neutral venue** | Yes (neutral_venue flag) | Yes (NeutralDixonColes) | Implicit | Yes (HFA per country) | Implicit |
| **Competition abstraction** | Full (league-agnostic) | EPL-hardcoded | Semi (configurable leagues) | 8 comps + UCL | Multi-league |
| **Knockout format** | No | No | No | UCL + league tiebreakers | No |
| **Monte Carlo** | No | No | No | Yes (10k iter) | No |
| **De-vigging methods** | 7 methods (Shin, power, etc.) | None | None | None | None |
| **Kelly criterion** | Full (fractional + portfolio) | None | Threshold filter only | None | Basic |
| **Walk-forward backtest** | Yes (full framework) | Implicit | Sliding window CV | None | Partial |
| **Evaluation metrics** | RPS, Brier, Ignorance | Implicit (FPL pts) | Accuracy, F1, Precision | None | Calibration plots |
| **Feature selection** | N/A | N/A | Boruta + correlation | N/A | PCA/EDA only |
| **Probability calibration** | N/A | N/A | Isotonic (optional) | N/A | None explicit |
| **Data source** | StatsBomb, Opta, scrapers | FPL API | football-data.co.uk | Wikipedia + APIs | Kaggle DB |
| **Persistent database** | No | SQLAlchemy/SQLite | No | No | No |
| **Cython optimization** | Yes | No | No | No | No |
| **Test suite** | Yes (pytest) | Yes | No | No | No |
| **Package / installable** | Yes (pip) | Yes (pip/uv) | No | No | No |
| **Stars (approx)** | 195 | 341 | ~500 | ~50 | ~100 |

---

## Top 5 Borrowable Architectural Ideas (Ranked by Value)

### #1 — penaltyblog: External Weight Injection Pattern (Value: Critical)

**What it is:** All statistical models accept a `weights` array as input. Time decay, recency, competition-importance weighting, and data source quality factors are all computed externally and injected at fit time. Models are stateless with respect to decay strategy.

**Why borrow it:** Your current codebase computes decay internally (xi parameter in DC). Separating decay from model fitting enables: (a) A/B testing decay functions without changing model code; (b) multi-factor weighting (recency × competition_importance × venue_quality); (c) the same model fitting code works across World Cup (few games, high importance) and league (many games, lower per-game importance) contexts without branching.

**Implementation sketch:** `model.fit(X, y, weights=decay_fn(dates, mode='exponential', xi=0.001) * competition_weight_fn(competition_ids))`

---

### #2 — penaltyblog: 7-Method De-Vigging with Shin's Model (Value: High)

**What it is:** Seven de-vigging methods (multiplicative, additive, power, Shin 1992, differential margin weighting, odds ratio, logarithmic) in a single `implied` module. Shin's model is theoretically superior — it assumes overround is proportional to probability square roots, modeling insider-information bookmaker behavior.

**Why borrow it:** Your current system uses one de-vigging approach. Shin's method has empirical support for being closer to "true" probabilities than multiplicative or additive methods, especially for low-probability outcomes (draws, upsets). Having all 7 lets you run RPS comparison across methods on your historical data to select optimal de-vigging per competition type.

**Gap in your project:** `skill/bet/kelly.py` has `MARKET_WHITELIST` and Kelly sizing but the de-vigging step before that appears to be a single method.

---

### #3 — AIrsenal: Calibrated Exponential Temporal Decay (Value: High)

**What it is:** `epsilon = 0.9` decay parameter calibrated empirically across 5 seasons of EPL data. Applied as `weights = exp(-epsilon * time_diff)`. Rescaling (`rescale_weights=True`) normalizes the weight sum to match count, so old data doesn't artificially reduce effective sample size. Different epsilon values for team model (0.9) vs player model (0.2).

**Why borrow it:** Your current xi=0.001 was set via backtest (Run 26 protocol). The AIrsenal pattern adds two improvements: (a) **rescale_weights** prevents the biased variance shrinkage from low effective-N when many old matches exist, and (b) having **competition-specific epsilon** (national leagues have 38-game recency baseline; World Cup has 7 games over a month) directly addresses your cross-competition generalization problem.

**Implementation sketch:** `epsilon_by_competition = {'WC': 1.2, 'UCL': 0.8, 'PL': 0.9}` — tune per competition via walk-forward backtest.

---

### #4 — ProphitBet: ML Ensemble Abstraction with Isotonic Calibration (Value: Medium-High)

**What it is:** `ClassificationModel` ABC with `build_classifier()` method unifying 9 sklearn estimators. Optional `CalibratedClassifierCV(method='isotonic')` wrapper. `StatisticsEngine` rolling features with shift(1) to prevent data leakage. Temporal sliding window CV respecting time ordering.

**Why borrow it:** Your framework is pure statistical (DC + ELO). An ML layer on top of your DC probability outputs — using rolling form features as additional signals — could capture non-stationarities that DC misses (e.g., mid-season managerial changes, tournament pressure). The isotonic calibration step is particularly valuable: even well-tuned DC models suffer systematic probability distortion in knockout formats.

**Key specific idea:** The `.shift(1).rolling(N).sum()` data-leakage-safe rolling feature pattern is immediately adoptable in your data pipeline.

---

### #5 — Club_Soccer_Season_Projections: xG→ELO Conversion + Multi-Competition Monte Carlo (Value: Medium)

**What it is:** Composite rating = 50% result-ELO + 25% xG-adjusted ELO + 25% squad-quality ELO. xG→ELO uses Poisson probability matrix weighted by `sqrt(goal_diff)` to compute ELO exchange — beyond just win/loss. Monte Carlo over 10k iterations with country-specific tiebreaker rules. UCL knockout format fully modeled.

**Why borrow it:** For World Cup and UCL prediction specifically, your current ELO doesn't incorporate xG (process quality) separately from results. The 50/25/25 weighting structure is a simple way to blend data sources with different reliability levels. More importantly, the separate `knockout_stage` class with two-leg aggregate logic is directly applicable to your UCL and WC bracket simulation.

**Gap in your project:** `skill/sim/montecarlo.py` already has `_R16_PAIRS/_QF_PAIRS/_SF_PAIRS` (Run 22 verified). The xG-weighted ELO exchange could feed into your attack/defense strength estimates rather than replacing them.

---

## Architectural Risk Notes

| Finding | Confidence |
|--------|-----------|
| penaltyblog time decay is external-only — no built-in xi | ✅ verified (source code) |
| AIrsenal epsilon=0.9 calibrated empirically across 5 seasons | ✅ verified (code comment) |
| ProphitBet isotonic calibration is optional, not default | ✅ verified (source code) |
| Club_Soccer xG→ELO uses normal distribution for margins, not Poisson | ✅ verified (source code) |
| FootballBettingModel 5.5% ROI reported over only 75 games — statistically unreliable | ⚠️ single source, small N |
| FootballBettingModel walk-forward testing — not rigorously verified, mostly notebook EDA | 🔍 not confirmed |

---

*Research complete. 40+ source files reviewed across 5 repositories.*
