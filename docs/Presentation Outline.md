# **HK Algo 2025: Proof of Concept Results**

## **Slide 1: Title Slide**

* **Title:** HK Algo 2025: Proof of Concept Results  
* **Subtitle:** Unlocking \+31.74% Profit through Automated Strategy Optimization  
* **Visual Suggestion:** Keep this clean and professional with your company logo and a subtle, dark-themed financial background.

## **Slide 2: The Challenges** 

**1\. Finding the Best Algo combinations**

* We needed to identify the absolute best-performing trading strategy out of **7,200** possible parameter combinations (genomes).

**2\. The Mathematical Time Barrier**

* To test these combinations across 5 different stocks, we needed to run **36,000** separate historical backtests. Doing this manually at 5 minutes per test would take over **600 hours** of non-stop work—a human impossibility.

**3\. Collaboration and Team Review**

* There was no standardized, visual way for the team to quickly compare crucial metrics like Win Rate, Profit, and Payoff Ratio side-by-side.

**4\. Data and Knowledge Store**

* Testing data was fragmented. We needed a way to permanently store thousands of algorithm variations so the team wouldn't have to re-test the same ideas in the future.  
* **Visual Suggestion:** Use a "roadblock" or "mountain" visual theme here. A graphic showing a massive pile of data/spreadsheets representing the 600 hours and 36,000 manual tests.

## **Slide 3: The Solution (How We Scaled It)**

**1\. The High-Speed Automated Engine**

* We engineered a fully automated testing architecture that successfully executed all **36,000** backtests with 100% mathematical accuracy in just **\~80 minutes** (down from 600+ hours).

**2\. Smart Filtering & Isolation**

* Instead of manual guessing, the system systematically combed through all 7,200 genomes and automatically isolated the top performers that beat the baseline original strategy.

**3\. Unified Visual Dashboard**

* We deployed a centralized reporting dashboard, allowing anyone on the team to instantly view, filter, and compare the most profitable genomes at a glance.

**4\. The "Strategy Library" Database**

* We successfully structured and saved all **7,200+** algorithm combinations and their 10-year historical performance into a permanent, searchable database for future research.  
* **Visual Suggestion:** Use a "flow/engine" visual here. A three-step diagram: \[7,200 Genomes Input\] ➡️ \[Automated Engine processing 36k tests in 80 mins\] ➡️ \[Clean Dashboard & Database Output\]. 

## **Slide 4: The Financial Impact (The Results)**

**1\. \+31.74% Increase in Total Profit from starting a $10,000 deposit.**

* The baseline algorithm yielded **$6,615** in profit.  
* By optimizing just 6 parameters, our top-performing genome (G\_6722) drove the profit up to **$8,978**—a clean increase of **\+$2,363**. 

**2\. 100+ Upgraded Strategies Discovered**

* We didn’t just find one winner. The automated system successfully identified over **100** different genomes that mathematically outperform the original strategy's Payoff Ratio (Average Win / Average Loss).

**3\. 100% Mathematical Accuracy**

* Every single backtest was executed without the human error associated with manual data entry, ensuring our profit projections are fully mathematically sound.  
* **Visual Suggestion:** A clean side-by-side bar chart showing Baseline Profit ($6,615) in gray next to Optimized Profit ($8,978) in green, with a bold "+31.74%" badge above it.

## **Slide 5: Your New Algorithm Database (Deliverables)**

*To ensure you get the most out of the attached [spreadsheet database](https://docs.google.com/spreadsheets/d/11a3m0AlIGsZ5O1HRVgjCP3zSCds-b_5OJGXmHKCP56U/edit?gid=2079366135#gid=2079366135), here is how it is structured:*

* **Dashboard View:** Your "executive summary." Use this tab for top-level performance charts and a quick glance at the absolute best genomes.  
* **PoC Results Sheet:** The finalized, averaged results for all 7,200 genomes across the 5 tested stocks. (Look for the highlighted G\_6722 row here\!).  
* **Parameter Tuning Sheet:** Your control center. In the future, you can easily adjust parameter ranges (like Minimums, Maximums, and Step Sizes) directly from this sheet without writing code.  
* **Raw Genomes Data (e.g., GENOMES 3888):** The granular, stock-specific performance data before our intelligent filtering was applied, preserved for your deeper research.  
* **Visual Suggestion:** Insert a clean screenshot of the "PoC Results Sheet" right here, drawing a colorful highlight box around the top-performing G\_6722 row so they know exactly what it looks like.

## **Slide 6: Next Steps / Future Roadmap**

**Phase 1: Production Scaling (Immediate)**

* **Goal:** Transition from PoC to a high-performance production environment.  
* **Key deliverables:** \* Migrate from Google Sheets to a dedicated Database and Multi-core Server.  
  * Implement AI-Assisted Ranging to determine optimal parameter ranges automatically.  
  * Implement Dynamic Allocation logic for custom-fitting optimal parameters to different stock codes.  
* **Estimation:** \~55–60 hours (Deployment \+ Full Optimization Run).

**Phase 2: Logic Modernization (Advanced Indicators)**

* **Goal:** Enhance algorithm intelligence by integrating market depth and volatility indicators.  
* **Key deliverables:**  
  * Implementation of VWAP (Volume Weighted Average Price).  
  * Implementation of Hurst Exponent logic.  
  * Testing new indicators to successfully filter out false positives.  
* **Estimation:** Requires 16–24 hours of R\&D for a final timeline.

**Phase 3: "Guard Dog" AI (Future Concept)**

* **Concept:** An independent AI model that reviews every signal generated by the algorithm.  
* Provides a final "Go / No-Go" decision based on broader market context.  
* Acts as a safety layer on top of the algorithmic signals.  
* **Estimation:** TBD (to be discussed after Phase 2 completion).  
* **Visual Suggestion:** A clean horizontal 3-step timeline graphic displaying Phases 1, 2, and 3 from left to right.

More detailed document with details of implementation you can find [here](https://docs.google.com/document/d/1xWu0PcY2S1FPX1IIQm78p3JsCSRK82c4EA8obR-RSv8/edit?tab=t.0#heading=h.7ol7qky0ovqm).