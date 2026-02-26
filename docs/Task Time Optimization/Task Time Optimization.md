# Task Time Optimization

Objective: Optimize the existing Python trading algorithm to reduce execution time from ~15 minutes per genome to under 1 minute. The target is to process 7,200 genomes in less than 2 hours (currently projected at 22.5 hours).

## Technical Requirements:

1. Code Optimization: Perform a deep research of the current codebase to identify bottlenecks. Implement performance improvements using data caching, vectorization (NumPy/Pandas), and loop optimization.

2. Strict Logic Preservation: The core algorithm must maintain 100% mathematical accuracy. Even minor changes to conditional logic are unacceptable as they significantly impact backtesting results.

3. Language: Use Python-native capabilities only.

## Data Handling & API Integration:

1. Input: The system must operate exclusively via Google Sheets API for command input and parameter retrieval.

2. Output & Limits: Since the final dataset will be large, implement logic to handle Google Sheets API rate limits and cell constraints (e.g., batch updates, payload optimization).

3. Redundancy: Implement a dual-storage system. Results must be saved to Google Sheets and duplicated locally into a file named Automated Results.csv by default.

## Deliverables:

- Refactored Python code with optimized execution logic.

- A report identifying previous bottlenecks and explaining the implemented optimizations.

- A robust data-logging module that manages API quotas and CSV backups.