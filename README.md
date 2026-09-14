# FundMix

**A portfolio optimisation engine that solves the problem backwards: you define the portfolio you want, and the engine works out what to buy and how much of each.**

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![CVXPY](https://img.shields.io/badge/CVXPY-quadratic%20programming-orange)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![License](https://img.shields.io/badge/license-AGPL--3.0-green)

---

## The problem

Every fund screener works the same way: you filter by category, compare, pick funds one by one, and at the end you look at whatever portfolio you ended up with. The portfolio is a consequence, not a decision.

FundMix reverses the flow. The user declares the profile they want:

> 60% US equities, 20% Europe, 10% emerging markets, 40% fixed income with a 3-year duration and an average BBB credit quality, bonds hedged to euro and equities unhedged, funds preferred over ETFs.

The engine returns the exact combination of assets that minimises the deviation from that profile, together with an audit of which objectives were met and which were not.

## Why not Markowitz

Modern Portfolio Theory requires two inputs that nobody knows: expected returns and the future covariance matrix. Both are estimated from historical data and are notoriously unstable, so small changes in the estimates produce radically different portfolios. You end up optimising noise.

FundMix takes forecasting out of the equation. It does not chase alpha, it maximises **profile compliance**. That turns a prediction problem into a convex optimisation problem with a guaranteed global optimum, solvable in milliseconds and auditable step by step.

---

## Contents

- [Mathematical formulation](#mathematical-formulation)
- [Objective hierarchy](#objective-hierarchy)
- [Data Shielding](#data-shielding-how-the-engine-behaves-when-data-is-missing)
- [Architecture](#architecture)
- [The investment universe](#the-investment-universe-a-boutique-quant-model)
- [Installation and usage](#installation-and-usage)
- [Repository layout](#repository-layout)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Mathematical formulation

Let `w ∈ ℝⁿ` be the vector of weights over `n` assets.

**Objective function**

```
minimise   Σ_k  λ_k · ( wᵀa_k − t_k · wᵀm_k )²   +   Σ_j  p_j(w)
```

where, for each objective `k`:

- `a_k` is the asset column for that metric (for example `Geo_RV_USA` or `RF_Duracion`),
- `t_k` is the target value declared by the user,
- `m_k` is the **applicability mask**: `1` for global metrics, `Expo_RV` for equity geography and sectors, and `Expo_RF + Expo_Monet` for any fixed-income metric,
- `λ_k` is the priority multiplier (see the hierarchy below),
- `p_j(w)` are the preference penalties, either linear or hinge-shaped.

**Constraints**

```
Σ wᵢ = 1                    fully invested
wᵢ ≥ 0                      long-only (UCITS compliant)
wᵀa_k = 0                   for every objective set to 0 (strict exclusion)
wᵀ·Expo_Alt ≤ max_alt       hard ceiling on alternative assets
```

### The core trick: linearising ratios without breaking convexity

The central technical challenge is that many metrics only make sense **over a slice of the portfolio**. The duration of the bond sleeve is the duration of the bonds, not an average diluted with equities, which have no duration at all.

The intuitive formulation would be a ratio:

```
Σ(wᵢ · durationᵢ) / Σ(wᵢ · is_bondᵢ) = target
```

But dividing by an expression containing the decision variable breaks the rules of Disciplined Convex Programming: the ratio of two linear functions is quasiconvex, not convex, and the solver could settle on a local optimum. CVXPY rejects it outright.

The solution is to clear the denominator:

```
Σ(wᵢ · durationᵢ) − target · Σ(wᵢ · is_bondᵢ) = 0
```

Both terms are linear, and a linear combination of linear functions is still convex. The engine therefore recovers the true weighted average of the bond sub-portfolio without ever dividing by `w`.

This idea is generalised through the mask system: any metric whose name starts with `RF_` is automatically evaluated over the rate-sensitive sleeve, and any `Geo_RV_*` or `Sec_*` metric over the equity sleeve. The masks are **continuous, not binary**, so a mixed fund holding 65% in bonds contributes exactly that 65% to portfolio duration. Labelling the fund "mixed" and counting it whole, or not counting it at all, introduces errors of half a year of duration or more.

---

## Objective hierarchy

The classic failure mode of a constrained optimiser is **over-specification**: the user asks for ten incompatible things and the solver returns *infeasible*, which is to say nothing at all. FundMix never returns nothing. It sorts objectives into three tiers and decides what to sacrifice first.

| Tier | Nature | What it covers | Behaviour |
|---|---|---|---|
| **1** | Hard constraint | Budget = 100%, no short selling, any objective declared at 0%, alternatives ceiling, strategy exclusions | Non-negotiable. Ask for 0% fixed income and not a cent goes into bonds |
| **2** | Penalty ×100 | Asset allocation, equity and bond geography, sectors, duration, credit quality | The engine fights to meet these. They explain most of the risk profile |
| **3** | Penalty ×1 | Vehicle (fund vs ETF), distribution policy, currency hedging per asset class, active/passive tilt, style bands | Tie-breakers. Sacrificed whenever they get in the way of Tier 2 |

Tier 3 preferences are **bidirectional**: a positive value means "I want this" and penalises assets that do not comply; a negative value means "I avoid this" and penalises the ones that do; zero means indifference.

Style bands use a **hinge loss**: if the exposure to a strategy falls inside the chosen range the cost is exactly zero, and only the excess outside the band is penalised. The user can express a conviction ("between 25% and 50% in Value") without forcing the engine to hit an impossible number.

---

## Data Shielding: how the engine behaves when data is missing

This is the design decision I am most pleased with, because it came out of a serious bug.

Credit quality is encoded on an inverted ordinal scale, from 1 (AAA) to 10 (D), and the optimiser minimises it. If an unrated bond is imputed as `0`, the engine concludes its quality is **better than AAA** and buys it heavily. An asset nobody has information about becomes, mathematically, the safest instrument in the universe.

The implemented rule is the opposite: when a value is missing, impute **the worst possible case**.

- Equities: `0.0`, harmless because shares carry no credit rating and the masks keep them out of the bond universe.
- Fixed income with no data: `12.0`, worse than the worst existing rating. The optimiser actively runs away from what it does not know.

And if a shortage of alternatives still forces those assets into the portfolio, the system detects that the resulting average quality exceeds the worst real value and, rather than displaying an invented rating, raises an insufficient-data warning. **A visible failure beats a plausible but false number.**

The same principle governs ingestion: if the factsheet does not publish a figure, the cell stays empty. Nothing is inferred, nothing is filled by analogy, nothing is estimated.

---

## Architecture

```
universo_fundmix.csv   →   FundMix.db   →   optimizer.py   →   app.py
   Golden Record           SQLite           CVXPY              Streamlit
   human-auditable         fast reads       convex engine      panel + audit
```

**Why both a CSV and a database.** The CSV is the source of truth: it is what gets edited, audited and version-controlled, and it is the only place where an empty cell remains distinguishable from a legitimate zero. SQLite is the engine's read layer, portable and serverless. The load is full and destructive, so the database can never drift from the CSV.

**Schema-agnostic ingestion.** Inserts do not use positional lists but dictionaries resolved against `PRAGMA table_info`. Adding or removing a column neither breaks the loader nor silently shifts the values of every other column.

### Data model

A single denormalised table of **51 columns**, deliberately not normalised to avoid `JOIN`s in the bulk read that feeds the solver.

| Block | Contents |
|---|---|
| Identity | ISIN (primary key), name, ticker, manager, product type, management style, strategy, distribution policy, currency, hedging |
| Cost and risk | TER, risk scale (SRRI 1-7) |
| Core exposure | `Expo_RV`, `Expo_RF`, `Expo_Monet`, `Expo_Alt` (sum to 1.0) |
| Equity geography | 11 columns: US, Europe, Japan, Canada, plus emerging markets broken down into China, India, Taiwan, Korea, Brazil and the rest |
| Bond geography | US, Europe, emerging, other |
| Sectors | Technology, healthcare, financials, consumer, industrials, energy, other |
| Fixed-income metrics | Duration, credit quality, % government, % corporate, yield |
| Informational | 1, 3 and 5-year returns; 3-year volatility, Sharpe, Alpha and Beta |

**Three conventions worth understanding:**

1. **Dual geographic segmentation.** `Geo_RV_*` and `Geo_RF_*` are independent axes. An investor may want exposure to US equities and no exposure whatsoever to US interest rates. Collapsing both into a single geographic variable would be a serious modelling error.

2. **Breakdowns are relative, not absolute.** `Geo_RV_*` sums to 1.0 *within the fund's equity sleeve*, which is how factsheets publish it. A mixed fund with 10% in equities, all of it American, has `Expo_RV = 0.10` and `Geo_RV_USA = 1.00`. The engine multiplies by the mask to recover the absolute 10%.

3. **Returns and ratios never enter the optimisation.** They live in the database for the final report, not for the decision. Optimising on past returns is return chasing; and a portfolio's Sharpe or volatility is not the weighted average of its components' but the result of the covariance matrix. Presenting them as optimisable would be mathematically false.

---

## The investment universe: a "boutique quant" model

**76 funds and ETFs, curated one by one.** Not 50,000 filled in halfway.

Choosing not to scrape the web at scale was deliberate, and it is probably the most important decision in the project. Free sources cover US ETFs well and European mutual funds very badly, which are precisely the instruments a portfolio built from Spain needs. A 51-variable schema patched together from partial sources turns into Swiss cheese, and an optimiser fed on nulls returns garbage that looks like precision.

The universe is built through a hybrid pipeline:

1. **MCP ingestion** of reliable public metrics (cost, risk, returns) from the broker's server.
2. **Assisted reading of official PDF factsheets** for everything no API publishes: real geographic breakdown, effective duration, average credit quality. The pipeline condenses each document, extracts the structure and validates the complete row before writing a single value.
3. **Manual curation** of whatever no source publishes, using purpose-built completeness auditing tools.

The official SRRI is also normalised using portfolio-manager judgement. UCITS regulation computes it from recent historical volatility, which produces anomalies such as an emerging markets fund reporting less risk than a developed markets one. The regulatory indicator ignores country risk, currency risk and liquidity risk. Feeding that anomaly into the model would make it overweight emerging markets believing they are safe.

---

## Installation and usage

```bash
git clone https://github.com/JorgedDios/FundMix.git
cd FundMix

python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

Build the database from the Golden Record:

```bash
python create_db.py              # creates the schema (destructive: recreates the table)
python skills/ingest_csv.py      # loads universo_fundmix.csv into SQLite
python skills/db_inspector.py    # audits integrity and lists pending fields
```

Launch the dashboard:

```bash
streamlit run app.py
```

Or drive the engine directly from Python:

```python
import optimizer

df = optimizer.get_data_from_db()

portfolio = optimizer.optimize_portfolio(
    df,
    user_targets={
        'Geo_RV_USA': 0.60,
        'Geo_RV_Europa': 0.20,
        'Expo_RF': 0.40,
        'RF_Duracion': 3.0,
        'RF_Calidad_Num': 4.0,      # BBB on the ordinal scale
    },
    preference_hedged_rf=1.0,        # bonds hedged to euro
    preference_hedged_rv=-1.0,       # equities unhedged
    preference_etf=-0.5,             # prefer funds over ETFs
    max_alt_weight=0.15,
)
```

### Command-line tools

| Script | What it does |
|---|---|
| `skills/ingest_csv.py` | Loads the Golden Record into SQLite. Aborts loudly if the schema does not match, so no data is lost in silence |
| `skills/db_inspector.py` | Audits integrity and generates the pending-field list. Requires each field based on the fund's **actual exposure**, not its label |
| `skills/auditar_huecos.py` | Completeness report per fund and per thematic block |
| `skills/rellenar_manual.py` | Console-assisted data entry, validating the resulting row before writing |
| `skills/procesar_pdfs.py` | PDF factsheet pipeline: `extract` → read → `apply` |
| `skills/limpiar_csv.py` | Structural repair of the CSV. Idempotent, and aborts when two duplicates hold conflicting data rather than choosing on its own |
| `skills/fix_geografia.py` | The only authorised exception to the shielding rule, restricted to a closed list of ISINs |
| `skills/podar_universo.py` | Removal of redundant or non-purchasable assets, with the reason documented per ISIN |
| `skills/check_dcp.py` | Convexity validation. **Mandatory before committing any change to the engine** |

Every tool that writes creates a timestamped backup, is idempotent, and validates the coherence of the resulting row rather than just the value being entered.

---

## Repository layout

```
├── app.py                      # Streamlit interface
├── optimizer.py                # CVXPY engine
├── create_db.py                # SQL schema
├── universo_fundmix.csv        # Golden Record: the source of truth
├── constitution/               # business and architecture rules
│   ├── mission.md              # what the project is and is not
│   └── tech-stack.md           # conventions and hard limits
├── features/                   # spec-driven development
│   ├── roadmap.md
│   └── 00X-.../                # spec.md · plan.md · tasks.md
└── skills/                     # auditing and ingestion tooling
```

The project follows **spec-driven development**: every increment has its specification, technical plan and task list with verifiable acceptance criteria, and no implementation may contradict the constitution. Reversed architecture decisions are documented too, along with the reasoning.

---

## Known limitations

What is not solved yet, for the sake of transparency:

- **The interface audit is out of step with the engine.** The `app.py` metrics still use the binary masks that predate the current engine version, so the deviations displayed do not match the ones the solver optimised. The correct logic already exists in `optimizer.py` and needs porting across.
- **Indifference and exclusion share the same value.** A geographic objective at 0 is read as a strict prohibition, which makes "I don't want Japan" indistinguishable from "Japan is irrelevant to me". Fixing it requires making objectives optional in the interface.
- **Shielding only covers credit quality.** When duration or yield is missing the default is `0.0`, a plausible figure that triggers no warning.
- **Uneven data coverage.** Spanish regulatory filings, the only source available for a good part of the domestic funds in the universe, publish no geographic or sector breakdown. That block is being completed by hand.
- **Narrow convexity validation.** `check_dcp.py` exercises a single scenario. It needs widening into a suite covering bands, exclusions and zero-valued objectives.
- **Tier scaling still to be calibrated.** Tier 2 is quadratic over small deviations while Tier 3 is linear over weights of order 1, so the effective priority between them is not the one the ×100 / ×1 ratio suggests.

---

## Roadmap

- **Phase 5 — Weighted optimisation.** Replace the fixed multipliers with coefficients the user controls, so they decide which objective gives way first when two of them collide.
- **Phase 6 — Internationalisation.** Bilingual interface, keeping the mathematical core language-agnostic.
- **Phase 7 — Clustering.** Unsupervised style classification and recommendation of equivalent alternatives to a given fund.
- **Phase 8 — Orchestration.** Automated monthly execution of the ingestion pipeline, matching the cadence at which asset managers refresh their holdings.

Documented backlog: cardinality control through a minimum-weight constraint (avoiding a mixed-integer reformulation), thematic sub-sectors, splitting the factor and strategy axes, and a manager mode with a custom universe.

---

## Disclaimer

FundMix is a personal project built for educational and research purposes. **It does not constitute financial advice or an investment recommendation.** Universe data is taken from official factsheets and may contain errors or be out of date.

## License

AGPL-3.0. See [LICENSE](LICENSE).

The source is fully open for study, modification and non-commercial use. If you want to use FundMix inside a commercial product, or run it as a hosted service without the obligations of the AGPL, a commercial licence is available: get in touch.
