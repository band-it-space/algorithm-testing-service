## Task Objective
The code processes a large number of combinations on historical data in the range of 10 years. This requires fast processing and parallelization of tasks.

## Details:
Currently, the code processes the queue sequentially, parallelizing only different `stock_codes` *(confirmation of this is required)*. It is necessary to parallelize this, considering that the code runs in docker, as a worker. There should be a limit on the number of simultaneous processes that can be configured in `.env`.

## Code optimization:
It is necessary for `algorithm_worker` to optimize logs so that there are not many of them to optimize the use of processor and memory resources. At the same time, there should be a debug mode separately for this worker, which will display the logs currently present (`.env` parameter).

## New API routes:
- Checking the connection (read/write) of a Google spreadsheet, when reading, parameters and their configurations should be returned.
- Checking the specified parameters for each genome *(if easy to implement)*: 
    - input: `genome_id`;
    - output: `its parameters`.

## Fixing past errors:
The calculation of the values ​​in the output table of results should be done
- Calculation of `Profit Delta (%)` for genomes, relative to the total profit/loss from the initial algorithm (for the initial algorithm it is =0).
- Calculation of `Win Rate (%)`, the ratio of the number of successful sales, to the total number.