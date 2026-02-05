# Task with Integraton Dynamic Fields

## Task Goal
Currently, the code processes algorithms with static parameters (buy_signals.py / sell_signals.py). The goal of this task is to dynamically change them and run the algorithm, checking which parameters will provide the best results.

## Input & Output
Input/output data is read/written to the Google Sheets table via API. An example of input data is given in the file "Input Rule Parameter IDs Sample.csv", an example of output data in "Output Results Sample.csv". Input data is a range that you need to iterate over with the specified step, and substitute into the corresponding values ​​​​of the algorithm parameters. Currently, all output data is written to CSV files in the "data" folder. Some individual output data are already calculated in the "summary" route.

## Notes
The parameter ID names are not perfect and do not include all possible parameters, so they can be changed to synchronize the name in the code.

The project is launched via Docker, and some functions are performed by workers, so it is important to take this into account.