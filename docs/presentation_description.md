# Presentation Description — HK Algo 2025 PoC Results

> **Purpose of this document:** A comprehensive brief for the designer to create a professional presentation. Contains all key data points, achievements, technical features, architecture details, and visual suggestions for each slide. The designer should select the most impactful information and arrange it visually.

---

## General Info

- **Project Name:** HK Algo 2025
- **Type:** Proof of Concept (PoC) — Automated Trading Algorithm Optimization Engine
- **Market:** Hong Kong Stock Exchange (HKEX)
- **Tech Stack:** Python, Redis, Docker, Google Sheets API, NumPy, Pandas
- **Date:** 2025–2026

---

## Slide 1 — Title Slide

**Title:** PoC Results | HK Algo 2025

**Subtitle:** Automated Trading Algorithm Optimization Engine

**Key message:** A fully automated system that discovers the best trading algorithm configuration out of thousands of possibilities — faster and more accurately than any manual process.

**Visual suggestion:** Clean, tech-oriented title design. Could include a subtle stock chart background or an abstract data-flow graphic. Logo if available.

---

## Slide 2 — The Problem / Why This Matters

**Headline:** The Challenge

**Content to choose from:**

- Manual trading strategy testing is slow, error-prone, and does not scale.
- A single algorithm has 33+ configurable parameters (buy signals, sell signals, stop-loss rules, energy indicators).
- Each unique combination of parameter values is called a "genome."
- With 6 variable parameters and multiple step sizes, the search space is **7,200+ unique genomes** to test.
- Each genome must be validated against **10 years of historical data** (2016–2026), covering ~2,481 trading days.
- Previously, testing one genome manually took **~15 minutes**. Testing all 7,200 would take **22.5 hours** — and that's for a single stock.
- For multi-stock validation (5 stocks), the problem multiplies: **7,200 genomes × 5 stocks = 36,000 runs**.
- Finding the best algorithm by hand is essentially impossible at this scale.

**Visual suggestion:** A comparison — "Manual" vs. "Automated" approach. Or a visual showing the explosion of combinations (parameter grid). Could use an hourglass or clock icon to emphasize time.

---

## Slide 3 — The Solution at a Glance

**Headline:** What We Built

**Content to choose from:**

- A **fully automated Python-based engine** that tests all 7,200 genome combinations across multiple stocks.
- The system replaced manual calculations with a **distributed, queue-based pipeline** powered by Redis.
- Three-stage architecture: Algorithm Worker → Result Worker → File Write Worker.
- All parameters are controlled from a **Google Sheets "Control Center"** — no coding needed to change the test configuration.
- Results are automatically aggregated, compared, and exported to both **CSV files** and **Google Sheets**.
- The system runs in **Docker containers** for reproducible, portable deployment.
- Designed to be **cloud-ready (AWS)** from day one.

**Visual suggestion:** A simplified architecture diagram showing the pipeline flow (API Request → Algorithm Queue → Result Queue → File Write Queue → Output). Clean boxes with arrows.

---

## Slide 4 — Key Results (The Headline Numbers)

**Headline:** PoC Results

**Key metrics (pick the most impactful for a visual "dashboard" layout):**

| Metric | Value | Note |
|---|---|---|
| **Original Strategy Profit** | ~$6,615 | Baseline genome G_000 |
| **Optimized Strategy Profit** | ~$8,978 | Best genome G_6722 |
| **Profit Delta** | +$2,363 | Additional profit found by the engine |
| **Improvement** | +31.74% | More profit than the original strategy |
| **Accuracy** | 100% | Validated across all 7,200 genomes |
| **Total Genomes Tested** | 7,200 | Full combinatorial search |
| **Better Algorithms Found** | 100+ | Outperforming the baseline |
| **Execution Time** | ~80 minutes | For the entire 7,200-genome run |
| **Multi-Stock Validation** | 5 stocks | Simultaneous testing across 5 different stock codes |

**Visual suggestion:** Large, bold numbers in a dashboard/KPI card layout. Use color-coding: green for profit, blue for speed. Possibly a "before → after" comparison card.

---

## Slide 5 — Performance Comparison: Before vs. After

**Headline:** From Manual to Machine Speed

**Before optimization:**

| Metric | Value |
|---|---|
| Time per genome | ~15 minutes |
| 7,200 genomes total time | ~22.5 hours |
| API calls per run | 7,200+ (redundant) |
| Indicator calculations | Recalculated every day (O(n²)) |
| Sort operations | ~15 per day per genome |
| Approach | Manual + semi-automated |

**After optimization:**

| Metric | Value |
|---|---|
| Time per genome | ~1 second |
| 7,200 genomes total time | ~80 minutes |
| API calls per run | ~1 (cached) |
| Indicator calculations | Pre-computed once (O(1) lookups) |
| Sort operations | 0 |
| Approach | Fully automated |

**Speed improvement: 300× per genome (from 5 minutes to 1 second after code optimization)**

**Total throughput improvement: ~17× (from 22.5 hours to ~80 minutes)**

**Visual suggestion:** A dramatic side-by-side comparison. Two columns (Before / After) with striking numbers. Or a speedometer/gauge graphic. A bar chart showing the time drop would also work well.

---

## Slide 6 — Performance Engineering: How We Achieved 300× Speed

**Headline:** Performance Engineering — 300× Faster

**The 7 bottlenecks identified and eliminated:**

1. **O(n²) Indicator Recalculation (60–70% of runtime)**
   - Every buy/sell signal recalculated SMA, Bollinger Bands, ATR from scratch on every trading day.
   - **Fix:** Pre-computed all indicators once using NumPy vectorized operations. O(1) array lookups instead of O(n) recalculation.

2. **Redundant API Calls (7,200× redundant)**
   - SPY reference data was fetched from the API for every single genome, even though it's identical.
   - **Fix:** Redis-based data caching with configurable TTL. >99.9% cache hit rate after warmup.

3. **Repeated Sorting (10–15% of runtime)**
   - Sell signal functions sorted the entire OHLCV dataset 10+ times per trading day.
   - **Fix:** Removed sorting from 13 sell functions. Data is pre-sorted once on load.

4. **Non-Vectorized Indicators (10–15% of runtime)**
   - SMA, RSI, ATR calculations used pure Python loops.
   - **Fix:** Replaced with NumPy `cumsum`, `pd.Series.rolling()`, `np.maximum()` vectorized operations.

5. **Energy Indicator Recalculation (5–10% of runtime)**
   - Energy indicators (E1–E5) were recalculated every day.
   - **Fix:** Pre-computed all rolling windows (5, 20, 250-day) once at startup.

6. **Date Parsing in Main Loop (~5% of runtime)**
   - Date strings were parsed to datetime objects on every iteration of the main loop.
   - **Fix:** Built a date index for O(1) lookups using binary search fallback.

7. **DataFrame.iterrows() (2–3% of runtime)**
   - Results processing used slow pandas `iterrows()`.
   - **Fix:** Replaced with vectorized `pd.to_numeric()` and `np.where()`.

**Visual suggestion:** A numbered list with icons, or a "waterfall chart" showing how each optimization chipped away at the total runtime. Could use a pie chart showing the bottleneck distribution before optimization.

---

## Slide 7 — Smart Filtering (Intelligent Search Space Pruning)

**Headline:** Smart Filtering — Save >40% Compute Time

**The concept:**

- Not all parameter values are equal. Some values consistently produce losing strategies — we call them **"toxic" parameters**.
- Smart Filtering identifies these toxic values **early** during optimization and automatically **removes all remaining genomes** containing them from the processing queue.
- Result: **>40% of compute time saved** without losing any good candidate algorithms.

**How it works (three mechanisms):**

1. **Gradual Elimination:**
   - Track the Payoff Ratio for every `(parameter_name, parameter_value)` pair across completed genomes.
   - If a value has enough observations (≥ MIN_OBSERVATIONS) and ALL results are below the quality threshold (Payoff Ratio < 2) → mark it as **toxic** → remove all remaining genomes with that value.

2. **Instant Elimination (Process of Elimination):**
   - When a genome produces a very bad result (Payoff Ratio < 1), check which parameter values are "not yet proven safe."
   - If exactly **ONE** unproven parameter value remains → it must be the toxic cause → eliminate it immediately.

3. **Multi-Stock Averaging:**
   - Genomes are evaluated across **all specified stock codes** (not just one).
   - A parameter is only deemed toxic if it performs poorly **universally** — eliminates noise from individual stock behavior.

**Example walkthrough (for technical audience):**
- G_001 (B1=0.55, B3=40, S5=0.9) → Payoff Ratio = 0.5 (terrible)
- G_002 (B1=0.55, B3=40, S5=0.7) → Payoff Ratio = 3.5 (great) → B1=0.55 and B3=40 are **cleared** (proven not toxic)
- G_003 (B1=0.65, B3=58, S5=0.9) → Payoff Ratio = 1.5 (still bad) → S5=0.9 now has 2 bad observations → **TOXIC** → Remove all remaining genomes with S5=0.9

**Customizable thresholds:**

| Parameter | Default | Purpose |
|---|---|---|
| MIN_PAYOFF_RATIO | 2 | Minimum acceptable Payoff Ratio |
| OUT_PAYOFF_RATIO | 1 | "Instant kill" threshold |
| MIN_OBSERVATIONS | 2 | Minimum evidence required |
| SMART_FILTERING_ENABLED | true | Feature toggle |

**Visual suggestion:** A funnel diagram showing how genomes are filtered out. Or a grid/matrix of parameter values with "toxic" ones highlighted in red and crossed out. An animation-style "elimination" visual would be powerful.

---

## Slide 8 — System Architecture

**Headline:** Three-Stage Queue-Based Pipeline

**Architecture overview:**

```
API Request → Algorithm Queue → Result Queue → File Write Queue → Output
```

**Stage 1 — Algorithm Worker:**
- Fetches OHLCV price data from the database.
- Iterates day-by-day through 10 years of trading data (~2,481 days).
- Evaluates all buy conditions (B1, B3, B8–B13, B18) and sell conditions (S1–S17).
- Manages trade entries, exits, stop-loss tracking.
- Calculates energy indicators (E1–E5).
- Writes raw signal CSV files.

**Stage 2 — Result Worker:**
- Reads the formatted CSV output.
- Calculates financial metrics: profit, win rate, payoff ratio, total wins/losses.
- Compares results against the baseline (G_000).
- Triggers cross-stock averaging when all stocks for a genome are complete.
- Triggers smart filtering evaluation.

**Stage 3 — File Write Worker:**
- Persists comparison results to CSV files.
- Thread-safe serialized writes to prevent data corruption.
- Dual storage: Google Sheets + local CSV backup.

**Concurrency model:**
- Multiple worker processes × multiple threads per process.
- Example configuration: 4 processes × 10 threads = 40 concurrent tasks.
- All PoC calculations used **8 CPU cores**.
- Workers pull jobs from a shared Redis queue using atomic operations — no pre-assignment needed.

**Visual suggestion:** A clean pipeline/flow diagram with three colored blocks (Algorithm → Result → File Write). Show queues between them. Optionally annotate with data flowing between stages (CSV, metrics, etc.).

---

## Slide 9 — The Trading Algorithm: Signal System

**Headline:** Multi-Signal Trading System — 18 Buy Signals + 17 Exit Strategies

**Buy Rule:** Enter a trade when:
- [B1 AND B3 AND B8 AND B9 AND B10 AND B11 AND B12 AND B13] — all conditions must be true simultaneously
- OR [B18] — Mark Minervini's Trend Template (alternative entry)

**Key buy signals explained (simplified):**

| Signal | What It Does |
|---|---|
| B1 | New high breakout + close in upper range of the day's bar |
| B3 | Bollinger Band Width contraction (volatility squeeze) |
| B8 | Higher lows pattern — confirming an uptrend |
| B9 | Close above midpoint of recent range — cancels weak setups |
| B10 | Rejects recent 250-day lows — avoids bottom-fishing |
| B11 | ATR not at extreme — avoids entering during peak volatility |
| B12 | 150-day MA growth check — ensures macro trend health |
| B13 | Relative performance vs. benchmark (HSI 2800) — stock must outperform the market |
| B18 | Minervini Trend Template — 8 conditions for confirmed Stage 2 uptrend |

**Exit / Stop-Loss signals (17 different exit strategies):**

| Signal | What It Does |
|---|---|
| S1 | ATR-based stop loss with hard cap (9.5% / 14.25%) |
| S4 | Profitable days ratio check after 50 days |
| S5 | Moving (trailing) stop — tightens over time |
| S6 | No new high in 76 days → exit stale positions |
| S7 | Dark candle pattern — two consecutive large red candles |
| S8 | ATR volatility expansion — exit on extreme turbulence |
| S9 | Energy level below threshold — momentum dying |
| S10 | ATR spike + drawdown from 90-day high |
| S11/S12 | Fibonacci retracement levels (0.382 / 0.236) |
| S13 | Close below 80-day closing low |
| S14 | Underperforming HSI benchmark for extended period |
| S15 | Rapid decline (>25% within 4 days) — crash protection |
| S16 | ATR surge + price decline — violent selloff |
| S17 | Range ratio exit after 150 days |

**Energy indicators (E1–E5):**
- Track the "health" / momentum of the position.
- Average energy level below 0.22 → triggers exit (S9).
- Combines: new highs, StochRSI, slope of close, relative performance, price position.

**Total configurable parameters:** 33+

**Visual suggestion:** A two-column layout: Buy Signals on the left (green), Sell Signals on the right (red). Could use a numbered list or icons. For the more detailed audience, show the logic tree: "Buy if [B1 AND B3 AND ... ] OR [B18]". Energy indicators could be a small supplementary section or a separate mini-slide.

---

## Slide 10 — Genome Optimization: How Parameters Are Tested

**Headline:** Systematic Parameter Search — 7,200 Combinations

**What is a genome?**
- A "genome" is a specific set of values for all configurable parameters.
- Example: G_000 is the baseline (original parameters). G_001 through G_7199 are variations.
- Each genome represents a unique trading strategy configuration.

**How the search works:**
1. Define parameter ranges and step sizes in Google Sheets (the "Control Center").
2. The system generates all possible combinations (Cartesian product).
3. Each combination is tested against 10 years of historical data.
4. Results are automatically ranked by Payoff Ratio, Profit Delta, Win Rate.

**6 variable parameters in PoC:**
- The PoC varied 6 parameters while keeping the rest fixed.
- This produced 7,200 unique combinations.
- All 7,200 were tested with **100% accuracy** — no approximations, no sampling.

**Multi-stock validation:**
- Each genome is tested on 5 different stock codes simultaneously.
- Results are **averaged across stocks** to eliminate stock-specific noise.
- A genome must perform well **universally**, not just on one stock.

**Result ranking:**
- Genomes are ranked by averaged metrics.
- The system identifies the **top-performing genome** and all genomes that outperform the baseline.
- 100+ genomes outperformed the original strategy in the PoC.

**Visual suggestion:** A grid/table showing parameter names on one axis and value ranges on the other. Highlight the "winning" genome. Or a scatter plot showing all 7,200 genomes plotted by Payoff Ratio, with the best ones highlighted. A funnel showing "7,200 tested → 100+ better → 1 best" could work well.

---

## Slide 11 — Google Sheets Control Center

**Headline:** Google Sheets as Command Center

**The Google Sheets setup serves as the central control and reporting hub:**

1. **Parameter Tuning Sheet:**
   - All parameter definitions and value ranges are configured here.
   - No coding required to change the test configuration.
   - Supports setting precise step sizes for each parameter.

2. **PoC Results Sheet (Final Aggregated):**
   - Displays final averaged results for all 7,200 combinations across 5 stock codes.
   - Shows core performance metrics: Profit Delta, Win Rate, Payoff Ratio.
   - Highlights the top-performing candidate.
   - Shows total count of combinations processed.

3. **Dashboard Sheet:**
   - Visualization and overview of results.
   - Charts and summary statistics.

4. **GENOMES 3888 (Raw Data):**
   - Raw performance data for 7,200 genomes on stock 3888.
   - Before Smart Filtering — all genomes included.

5. **SMART FILTERING 3888 (Optimized Data):**
   - Optimized results after applying Smart Filtering logic.
   - Shows which parameter values were eliminated and why.

6. **500 STOCKS (Stress Test):**
   - Large-scale stress test comparing the Baseline algorithm against the "Best Candidate."
   - Tested across **500 different stock codes**.
   - Validates robustness beyond the initial 5-stock validation.

**Technical note:** The system handles Google Sheets API rate limits with token-bucket rate limiting, exponential backoff for 429 errors, and batch row updates with chunking.

**Visual suggestion:** A screenshot or mockup of the Google Sheets layout showing different tabs. Annotate the key areas. Could also show a flow: "Configure Parameters → Run Engine → View Results" all within Google Sheets.

---

## Slide 12 — Scalability & Cloud Readiness

**Headline:** Horizontally Scalable — AWS Ready

**Scalability features:**

- **Linear Scaling:** More CPU cores = proportionally faster processing.
- **Docker-based deployment:** `docker-compose up` and you're running.
- **Cloud readiness (AWS Ready):**
  - Containerized architecture maps directly to ECS/EKS.
  - Redis queue can be replaced with ElastiCache.
  - Worker count is configured via environment variables — no code changes.
- **Infrastructure flexibility:**
  - Works on a single developer laptop or a 64-core cloud server.
  - All PoC calculations were performed with 8 CPU cores.
  - Horizontally scale by simply increasing worker processes.

**Concurrency breakdown:**

| Component | Processes | Threads/Process | Total Concurrent |
|---|---|---|---|
| Algorithm Workers | N (configurable) | M (configurable) | N × M |
| Result Workers | N | M | N × M |
| File Write Workers | N | M | N × M |

**Example:** 4 processes × 10 threads = 40 genomes processed simultaneously.

**What this means for production:**
- PoC used 8 cores → ~80 minutes for 7,200 genomes.
- 32-core server → estimated ~20 minutes for 7,200 genomes.
- 64-core server → estimated ~10 minutes for 7,200 genomes.
- Scale further by adding more parameter variations — the system handles it linearly.

**Visual suggestion:** A scaling graph showing cores vs. processing time (linear relationship). Or a cloud infrastructure diagram showing Docker containers scaling out. AWS/cloud logos could be placed tastefully.

---

## Slide 13 — Full Automation & Validation

**Headline:** From Manual to Fully Automated

**Automation journey:**
- **Before:** Manual calculations → semi-automated scripts → error-prone → slow iteration.
- **After:** One API call triggers the entire pipeline: data fetch → algorithm execution → result aggregation → Google Sheets export.

**Validation rigor:**
- **100% mathematical accuracy** — no approximations, no sampling, no shortcuts.
- Every optimization change was validated by comparing outputs against reference results field-by-field.
- Validation framework includes:
  - Unit tests for all vectorized indicators.
  - Reference output comparison (buy signals, sell signals, energy levels).
  - Floating-point tolerance for ATR calculations (±0.0001).
  - 10 diverse test genome configurations for regression testing.

**Dual storage for safety:**
- All results are saved to both **Google Sheets** and **local CSV files**.
- Rate limiting and exponential backoff handle API quotas.
- Atomic file writes with temp-file-and-rename pattern prevent data corruption.

**Visual suggestion:** A timeline or journey map: Manual → Semi-Automated → Fully Automated. Or a checklist of "100% accuracy validated" checkpoints with green checkmarks.

---

## Slide 14 — Output Data & Results Structure

**Headline:** Comprehensive Results Reporting

**Output files produced by the engine:**

1. **Automated Results.csv** — Averaged results across all stock codes per genome.
   - Genome ID, Trade Count, Profit Delta (%), Win Rate Delta (%), Total Win ($), Total Loss ($), Trades Win, Trades Loss, Avg Win ($), Avg Loss ($), Payoff Ratio.
   - Dynamic parameter columns showing which values vary.

2. **Automated Results Per Genome.csv** — Per-stock breakdown.
   - Same metrics but for each (Genome ID, Stock Code) pair.

3. **Comparison Results.csv** — Side-by-side comparison against the API baseline.

4. **General Results.csv** — Aggregated summary statistics.

5. **Google Sheets** — Same averaged results, automatically uploaded.

**Key performance metrics tracked:**

| Metric | Description |
|---|---|
| Profit Delta (%) | How much more/less profit vs. baseline |
| Win Rate Delta (%) | How much better/worse the hit rate is |
| Payoff Ratio | Average Win / Average Loss — core quality metric |
| Trade Count | Number of trades executed by the strategy |
| Total Win ($) | Sum of all winning trades |
| Total Loss ($) | Sum of all losing trades |
| Avg Win ($) | Average size of a winning trade |
| Avg Loss ($) | Average size of a losing trade |

**Visual suggestion:** A sample results table or dashboard mockup showing top-5 genomes. Highlight the best genome in gold/green. Show the column headers to give a sense of the data richness.

---

## Slide 15 — The Winning Genome

**Headline:** The Best Algorithm — G_6722

**Direct comparison:**

| Metric | Original (G_000) | Optimized (G_6722) | Delta |
|---|---|---|---|
| Profit | ~$6,615 | ~$8,978 | +$2,363 (+31.74%) |

**What this means:**
- Without changing the fundamental trading logic, just by tuning 6 parameters, the engine found a configuration that produces **31.74% more profit**.
- This is not overfitting to one stock — validated across 5 different stocks.
- 100+ other genomes also outperformed the baseline — there's a rich landscape of good configurations.

**Visual suggestion:** A large "before → after" comparison with a prominent "+31.74%" or "+$2,363" number. Could use a bar chart, a gauge, or a simple card layout. Green color for the improvement. Crown/trophy icon on the winning genome.

---

## Slide 16 — 500-Stock Stress Test

**Headline:** Battle-Tested Across 500 Stocks

**What was tested:**
- The Baseline algorithm (G_000) was compared against the Best Candidate from PoC Results across **500 different Hong Kong stock codes**.
- This is the ultimate robustness check — does the optimized algorithm hold up outside the training stocks?

**Why this matters:**
- Overfitting to a few stocks is a common pitfall in algorithmic trading.
- Testing on 500 stocks ensures the improvement is **structural**, not accidental.
- The optimized algorithm demonstrated consistent outperformance across the broader market.

**Visual suggestion:** A map or grid of 500 small icons/dots showing stocks tested. Or a histogram showing the distribution of Profit Delta across all 500 stocks, with most being positive (shifted to the right of zero).

---

## Slide 17 — Next Steps / Future Roadmap

**Headline:** Roadmap — What's Next

**Phase 1: Production Scaling (Immediate)**
- **Goal:** Transition from PoC to a high-performance production environment.
- **Key deliverables:**
  - Migrate from Google Sheets to a **dedicated Database** and **Multi-core Server**.
  - Implement **AI-Assisted Ranging** to determine optimal parameter ranges automatically.
  - Implement **Dynamic Allocation logic** for custom-fitting optimal parameters to different stock codes.
- **Estimation:** ~55–60 hours (Deployment + Full Optimization Run).

**Phase 2: Logic Modernization (Advanced Indicators)**
- **Goal:** Enhance algorithm intelligence by integrating market depth and volatility indicators.
- **Key deliverables:**
  - Implementation of **VWAP** (Volume Weighted Average Price).
  - Implementation of **Hurst Exponent** logic.
  - Testing new indicators to successfully filter out false positives.
- **Estimation:** Requires 16–24 hours of R&D for a final timeline.

**Phase 3: "Guard Dog" AI (Future Concept)**
- **Concept:** An independent AI model that reviews every signal generated by the algorithm.
- Provides a final **"Go / No-Go" decision** based on broader market context.
- Acts as a safety layer on top of the algorithmic signals.
- **Estimation:** TBD (to be discussed after Phase 2 completion).

**Visual suggestion:** A timeline/roadmap graphic with three phases. Phase 1 highlighted as "current/next." Each phase could have an icon (server for Phase 1, brain/chart for Phase 2, AI/robot for Phase 3). Use a left-to-right flow.

---

## Slide 18 — Technical Summary / Architecture Deep Dive (optional, for technical audience)

**Headline:** Under the Hood

**Technology stack:**

| Component | Technology |
|---|---|
| Core Engine | Python 3.8+ |
| Queue System | Redis + RQ (Redis Queue) |
| Data Processing | NumPy, Pandas |
| Containerization | Docker, Docker Compose |
| API Framework | FastAPI (HTTP endpoints) |
| Data Storage | Google Sheets API + CSV |
| Caching | Redis (data cache with TTL) |
| Rate Limiting | Token bucket algorithm |
| Deployment | Docker Compose (local), AWS-ready |

**Signal processing pipeline per genome:**
1. Fetch OHLCV data (cached in Redis after first call).
2. Pre-compute all indicators (SMA, Bollinger Bands, ATR, RSI, rolling windows) once — vectorized.
3. Build date index for O(1) day lookups.
4. Iterate through all trading days:
   - If **Free (no position):** Evaluate all buy conditions → enter trade if conditions met.
   - If **In Position:** Evaluate all sell/stop conditions → exit if triggered.
   - Track energy level, stop-loss, position age throughout.
5. Output raw signals CSV.
6. Calculate financial metrics (profit, win rate, payoff ratio).
7. Compare against baseline genome.
8. Aggregate across multiple stocks.
9. Trigger smart filtering evaluation.
10. Export to Google Sheets + CSV.

**Code quality:**
- 33+ algorithm parameters fully parameterized (no hardcoded magic numbers).
- Comprehensive test suite covering buy signals, sell signals, energy indicators, smart filtering.
- Validation framework ensures 100% accuracy after any code change.
- Modular architecture: signals, indicators, workers, services — all separated.

**Visual suggestion:** A more detailed architecture diagram for technical audiences. Show Redis, Docker containers, workers, data flow. Could be a supplementary slide or appendix.

---

## Appendix — Raw Numbers & Data Points for Slide Design

These are additional data points the designer can use for visual elements, callout boxes, or infographic-style decorations:

| Data Point | Value |
|---|---|
| Total genomes tested | 7,200 |
| Trading days per genome | ~2,481 (10 years) |
| Total trading days processed | 7,200 × 2,481 = ~17.8 million |
| Buy signal conditions | 18 (B1–B18) |
| Sell/exit signal conditions | 17 (S1–S17) |
| Energy indicators | 5 (E1–E5) |
| Configurable parameters | 33+ |
| Variable parameters in PoC | 6 |
| Stocks validated | 5 (primary) + 500 (stress test) |
| CPU cores used in PoC | 8 |
| Cache hit rate | >99.9% |
| Speed improvement per genome | 300× (5 min → 1 sec) |
| Total time improvement | ~17× (22.5 hrs → ~80 min) |
| Compute time saved by Smart Filtering | >40% |
| Better algorithms found | 100+ |
| Profit improvement of best genome | +31.74% (+$2,363) |
| Mathematical accuracy | 100% |
| API redundancy reduction | >99.9% |
| Sort operations eliminated | 100% (from ~15/day to 0) |

---

## Design Notes for the Designer

1. **Color palette suggestion:** Use a professional finance/tech palette. Blues and dark grays for backgrounds, green for positive metrics (profit, improvement), red for negative/toxic values, gold/amber for highlights.

2. **Font recommendation:** A clean sans-serif font (e.g., Inter, Montserrat, or similar). Use monospace for code snippets or genome IDs.

3. **Slide count:** The slide list above is comprehensive — aim for 12–15 slides for a 20-minute presentation. Slides 2–7 and 15–17 are the most important. Slides 8, 9, 10, 18 can be condensed or placed in an appendix for technical audiences.

4. **Key visual elements:**
   - Dashboard-style KPI cards for key metrics.
   - Before/After comparison layouts.
   - Pipeline/flow diagrams for architecture.
   - Funnel diagrams for smart filtering.
   - Timeline for roadmap.
   - Tables with alternating row colors for data-heavy slides.

5. **Tone:** Professional, confident, data-driven. This is a PoC success story — the numbers speak for themselves. Avoid hype; let the metrics do the talking.

6. **Animations:** Minimal. Use entrance animations sparingly for key numbers. No distracting transitions between slides.
