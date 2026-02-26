# Presentation Description — HK Algo 2025 PoC Results

> **Purpose of this document:** A brief for the designer to create a professional, self-standing presentation (no speaker). Visually driven, concise, focused on business value and results. The audience should understand WHAT problems we solved and WHAT results we achieved — not how the code works internally.

> **Key context:** The customer already has a profitable trading algorithm. We proposed optimizing its parameters (coefficients in the formulas) to increase profitability. The PoC was conducted to prove — before committing to the full project — that measurable improvements are achievable. The algorithm was originally built for real-time trading; running it thousands of times for optimization required a complete re-engineering of its performance. The results exceeded expectations.

> **Presentation style:** Self-presenting (no speaker). Text must be minimal — use large numbers, comparison visuals, simple diagrams, and clear takeaways. Every slide should have one clear message understood in 10–15 seconds of reading.

---

## General Info

- **Project Name:** HK Algo 2025
- **Type:** Proof of Concept (PoC) — Trading Algorithm Optimization
- **Market:** Hong Kong Stock Exchange (HKEX)
- **Date:** 2025

---

## Slide 1 — Title Slide

**Title:** HK Algo 2025: Proof of Concept Results

**Subtitle:** Unlocking +31.74% Profit through Automated Strategy Optimization

**Visual suggestion:** Clean and professional with company logo. Dark-themed financial background — subtle, abstract chart lines or data patterns. No clutter. Project name + subtitle + date only.

---

## Slide 2 — The Challenges

**Headline:** The Challenges We Solved

**4 challenge blocks (icon + short text for each):**

**1. Finding the Best Parameter Combination**
- The algorithm has **33+ tunable coefficients** (entry thresholds, exit rules, stop-loss levels). The current values were set manually.
- With 6 variable parameters, there are **7,200 possible combinations** to test. Which one performs best? The only way to know is to test them all.

**2. The Time Barrier**
- Each combination must be backtested on **10 years** of historical data.
- To test all 7,200 combinations across **5 different stocks**, we needed to run **36,000 separate backtests**.
- At the original algorithm speed (~5 min per test), that's over **3,000 hours** of computation — an impossibility.

**3. Team Collaboration & Review**
- There was no standardized way to quickly compare crucial metrics like Win Rate, Profit, and Payoff Ratio across thousands of results side-by-side.

**4. Data & Knowledge Preservation**
- Testing data was fragmented. The team needed a permanent, structured way to store all algorithm variations and their historical performance to avoid re-testing the same ideas in the future.

**Visual suggestion:** Use a "roadblock" or "mountain" visual theme. 4 blocks or cards, each with a number, icon, and 1–2 lines. The **3,000 hours** and **36,000 backtests** numbers should stand out. This slide sets up the "before" — the next slide is the "after."

---

## Slide 3 — The Solution

**Headline:** How We Solved It

**4 solution blocks matching the 4 challenges (icon + short text):**

**1. High-Speed Automated Engine → solved Challenge 1 & 2**
- We engineered a fully automated testing engine that executed all **36,000 backtests** with **100% mathematical accuracy** in just **~80 minutes**.
- Processing speed: optimized from ~5 minutes down to **~1 second per test** — a **300× speedup**.

**2. Smart Filtering → solved Challenge 1 (faster)**
- The engine automatically identifies **"toxic" parameter values** that consistently produce losses and skips all remaining combinations containing them.
- Result: **>40% additional compute time saved** — without missing any good configuration.

**3. Unified Visual Dashboard → solved Challenge 3**
- We deployed a centralized reporting dashboard, allowing anyone on the team to instantly view, filter, and compare the most profitable algorithm configurations at a glance.

**4. Strategy Library & Database → solved Challenge 4**
- All **7,200+ algorithm variations** and their 10-year historical performance are permanently stored in a structured, searchable database for future research and reference.

**Visual suggestion:** A "flow/engine" visual. Either 4 solution cards matching the 4 challenge cards from the previous slide, or a three-step flow diagram: [7,200 Genomes Input] → [Automated Engine: 36,000 tests in ~80 min] → [Dashboard & Database Output]. Show the transformation from problem to solution. Keep it clean — each block is a headline + 1–2 lines max.

---

## Slide 4 — The Financial Impact

**Headline:** The Results

**The hero number (large, prominent, center of slide):**

> **+31.74% Increase in Total Profit**

**Comparison bar chart or two KPI cards side by side:**

| | Baseline Algorithm | Optimized (Best Found) |
|---|---|---|
| **Profit (from $10,000 deposit)** | **$6,615** | **$8,978** |
| **Difference** | — | **+$2,363** |

**Supporting metrics (3 smaller cards or badges below the chart):**

| Metric | Value |
|---|---|
| 🏆 **Better Strategies Found** | **100+** configurations that outperform the original |
| ✅ **Mathematical Accuracy** | **100%** — every backtest fully calculated, no sampling, no human error |
| 🛡️ **Robustness Check** | Battle-tested across **5 validated stocks** + stress-tested on **500 stocks** |

**Visual suggestion:** This is the "money slide." The **+31.74%** should be the largest element on the page. Use a side-by-side bar chart: Baseline Profit ($6,615) in gray next to Optimized Profit ($8,978) in green, with a bold "+31.74%" badge above it. Below, the three supporting metrics as small cards. The 500-stock stress test reinforces credibility — it's not just one lucky stock.

---

## Slide 5 — Smart Filtering

**Headline:** Smart Filtering — Built-In Intelligence

**Core message (3 short blocks + visual):**

- Not all parameter values are worth testing. Some consistently produce losses — we call them **"toxic" parameters.**
- The engine **automatically detects and eliminates** bad values early, skipping all remaining combinations that contain them — in real time, during the run.
- **Result: >40% compute time saved** — without missing any good configuration.

**Simple visual — funnel or elimination diagram:**

```
7,200 genomes  →  Smart Filtering eliminates toxic combinations  →  Only promising genomes fully processed
     100%                    removes ~40%                              best candidates remain
```

**How it works (simplified, one visual step each):**

1. 📊 **Track** — Monitor results per parameter value as genomes complete.
2. 🔍 **Detect** — If a value consistently produces losses across multiple tests, flag it as toxic.
3. ⏭️ **Skip** — Automatically remove all remaining combinations with that toxic value from the queue.

**Why this matters:**
> On larger runs with 100,000+ genomes, Smart Filtering will save days of processing. The intelligence scales with the problem.

**Visual suggestion:** A funnel diagram: wide at the top (7,200 genomes), narrowing (filtering), output at the bottom (best candidates). Or a grid of colored blocks: green (good), red (toxic, crossed out), gray (skipped). The ">40% compute savings" should be a prominent callout. Keep it visual, not text-heavy.

---

## Slide 6 — Your Algorithm Database

**Headline:** What You Get — Your Strategy Database

**Intro line:**
> All results are stored in the [attached spreadsheet database](https://docs.google.com/spreadsheets/d/11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U/edit?gid=2079366135#gid=2079366135). Here's how it is structured:

**5 tabs explained (icon + one-liner each):**

| Tab | What's Inside |
|---|---|
| 📊 **Dashboard** | Executive summary — top-level performance charts and a quick glance at the best genomes. |
| 🏆 **PoC Results** | Finalized, averaged results for all 7,200 genomes across 5 stocks. Look for the highlighted **G_6722** row — the top performer. |
| 🎛️ **Parameter Tuning** | Your control center. Adjust parameter ranges (Minimums, Maximums, Step Sizes) directly — no coding required. |
| 📋 **Raw Genomes Data** *(e.g., GENOMES 3888)* | Granular, stock-specific performance data before filtering — preserved for deeper research. |
| 🛡️ **500 Stocks** *(Stress Test)* | Large-scale robustness check — Baseline vs. Best Candidate compared across 500 stock codes. |

**Key point (callout):**
> This database is permanent. Every algorithm variation and its 10-year performance is stored and searchable. No need to re-test the same ideas in the future.

**Visual suggestion:** Insert a clean screenshot of the "PoC Results" sheet, with a colorful highlight box around the G_6722 row. Annotate the tabs visually (like a tab bar with labels). This slide should feel like a tangible deliverable — "here's what you're getting."

---

## Slide 7 — Next Steps

**Headline:** Roadmap — What's Next

**Three phases as a horizontal timeline:**

**Phase 1: Production Scaling** *(Immediate)*
- Migrate from Google Sheets to a dedicated database & multi-core server.
- AI-assisted ranging to determine optimal parameter ranges automatically.
- Dynamic allocation — fit optimal parameters per stock code.
- *Outcome: Full-scale optimization across the entire stock universe.*
- **Estimation:** ~55–60 hours.

**Phase 2: Logic Modernization** *(Advanced Indicators)*
- Integrate VWAP (Volume Weighted Average Price) and Hurst Exponent into the algorithm.
- Better filtering of false positive signals.
- *Outcome: Higher quality trades, fewer bad entries.*
- **Estimation:** 16–24 hours of R&D for a final timeline.

**Phase 3: "Guard Dog" AI** *(Future Concept)*
- An independent AI model reviews every trade signal.
- Provides a final "Go / No-Go" decision based on broader market context.
- *Outcome: An extra safety layer on top of the algorithm.*
- **Estimation:** TBD (after Phase 2 completion).

**Footer link:**
> More detailed document with implementation details: [link to full specification](https://docs.google.com/document/d/1xWu0PcY2S1FPX1IIQm78p3JsCSRK82c4EA8obR-RSv8/edit?tab=t.0#heading=h.7ol7qky0ovqm).

**Visual suggestion:** A clean horizontal 3-step timeline from left to right. Phase 1 highlighted/emphasized as "current/next." Each phase gets an icon (🖥️ server, 📊 chart, 🤖 AI) and 2–3 bullet points max. Keep it forward-looking and confident.

---

## Slide 8 — Summary

**Headline:** PoC Summary

**4 key takeaway cards (large, visual, dashboard-style):**

| | |
|---|---|
| 📈 **+31.74% profit increase** | Optimized genome vs. baseline — validated across multiple stocks |
| 🧬 **7,200 combinations × 5 stocks** | 36,000 backtests, 100% accuracy, 100+ better strategies found |
| ⚡ **From 3,000 hours to 80 minutes** | 300× per-test speedup + Smart Filtering saves >40% more |
| 🚀 **Ready to scale** | Cloud-ready engine, permanent strategy database, clear roadmap |

**Closing line (centered, confident):**
> The PoC proves the approach works and already delivers measurable results. The engine is built, tested, and ready for production scaling.

**Visual suggestion:** A clean summary dashboard — 4 large KPI cards with icons, bold numbers, and one-line labels. Below them, the closing statement in slightly smaller text. This is the last impression — it should feel conclusive, confident, and forward-looking. Include company logo.

---

## Design Notes for the Designer

1. **This presentation must work without a speaker.** Every slide must deliver its message through visuals + minimal text. A reader should fully understand the story on their own.

2. **Narrative arc:** Challenges (Slide 2) → Solutions (Slide 3) → Results/Proof (Slide 4) → Key Feature (Slide 5) → Deliverables (Slide 6) → Future (Slide 7) → Summary (Slide 8). Each slide builds on the previous one.

3. **Color palette:** Professional finance/tech — dark blues, grays, whites. Green for positive results and improvements. Red sparingly for "toxic" values on the Smart Filtering slide. Gold/amber for hero numbers (+31.74%, 300×).

4. **Font:** Clean sans-serif (Inter, Montserrat, or similar). Hero numbers should be large (40–60pt+). Body text minimal and secondary.

5. **Slide count:** 8 slides total (1 title + 6 content + 1 summary). Do NOT add more.

6. **Core visual elements needed:**
   - Before/After bar chart (Slide 4 — profit comparison)
   - Funnel diagram (Slide 5 — smart filtering)
   - Google Sheets screenshot with highlighted row (Slide 6 — deliverables)
   - Horizontal timeline (Slide 7 — roadmap)
   - KPI/dashboard cards (Slides 3, 4, 8)
   - Challenge→Solution matching layout (Slides 2–3)

7. **Tone:** Confident, professional, results-driven. No hype — the numbers speak for themselves.

8. **Animations:** Minimal to none. Should read well as a static PDF or printed deck.

9. **Logo/branding:** Include company logo on title and closing slides.