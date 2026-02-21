**HK Algo 2025**  
\==================

**Buy Rule** \---\> Buy if  
\[B1 AND B3 AND B8 AND B9 AND B10 AND B11 AND B12 AND B13\]  
OR  
\[B18\]

B1. \[  
 New high in the past {20D}  
 OR  
 CLOSE ABOVE Bollinger Band ({51}, {1.9}) but not deviating from {51MA} by {25%}  
 \]  
 AND  
 \[  
 close is higher than \[Low \+ {0.65} \* (High \- Low)\]  
 \]

\++ B3. BBW \= BBW(Close, {21}, {2}), SMA_BBW \= SMA(BBW, {72}), Slope of LR(SMA_BBW), {58}) \< 0

\++ B8. {46D} low \> T-{47D} to T-{270D} low

\++ B9. THEN CANCEL Buy if Close \< (Last {50D} High \+ Last {50D} Low) /2 and high Date is earlier than low date

\++ B10. if 250D low happens within {68} days before breakout, THEN CANCEL Buy.

\++ B11. IF Current ATR(22) is higher than {87%} of maximum ATR(22) in the past {126} day, THEN CANCEL Buy.

\++ B12. If 150D SMA has risen {16%} in the past {50} days AND Today high is deviating from 150DMA by 20%, THEN CANCEL Buy.

\++ B13. CANCEL Buy if the stock is underperforming 2800 for {19}-Day AND {60}-Day look back periods.

B18. Mark Minervini's Trend Template \- Criteria for Confirmed Stage 2 Uptrend  
 B18(1) The current stock price is above both the 150-day (30-week) and the 200-day (40-week) moving average price lines.  
 B18(2) The 150-day moving average is above the 200-day moving average.  
 B18(3) The 200-day moving average line is trending up for 1 month.  
 B18(4) The 50-day (10-week) moving average is above both the 150-day and 200-day moving averages.  
 B18(5) The current stock price is trading above the 50-day moving average.  
 B18(6) The current stock price is at least 30 percent above its 52-week low.  
 B18(7) The current stock price is within at least 25 percent of its 52-week high.  
 B18(8) Average BBW in the past {21} days is small than {22%} of BBW in the past {82} days and Price is also above BB({21},2) upper band

**Stop Rule** \---\> Stop if  
\[S1 OR S4 OR S5 OR S6 OR S7 OR S8 OR S9 OR S10 OR S11 OR S12 OR S13 OR S14 OR S15 OR S16 OR S17\]

S1. Use \[CLOSE \- {3.7}\*ATR({22})\] as stop position, if stop loss is \> {20%}, set stop loss at {9.5%} instead of close of \[CLOSE \- {3.7}\*ATR({22})\].  
 BUT IF if stop loss is \> 30%, set stop loss at 1.5\*{9.5}% instead of close of \[CLOSE \- {3.7}\*ATR({22})\].

S4. Enable this rule on the {50}th trading day after issuing Buy.  
 Let A \= counting number of trading day whereas Daily Close \> 150D MA  
 If A/{50} \< {50%} and {50} Days gain is \< {5%} then exit trade

S5. Effective on or after {45} days  
 Initial stop \= entry price \+ {0.62}\*ATR(20)  
 Push up stop by {0.62}\*ATR(20) every {25} days.

S6. Effective after 50 days, if no new {90D} high in the last {76} days, then stop

S7. Exit the position if (open \- close) \> {2} x ATR(22) for two consecutive trading days

S8. IF Current ATR({100}) is higher than {74%} of maximum ATR(22) in the past 126 day, THEN EXIT the position if (open \- close) \> {2.4} x ATR({100}) for \[3 out of 5\] trading days

S9. Exit by making use of energy: IF {16-day} average energy level \< {0.22}, THEN EXIT.

S10. STOP if the following conditions are met:  
 1\. ATR(10) \> {2.6} \* ATR(100)  
 2\. Drawdown from 90D High \> {5%}

S11. EFFECTIVE after {300} Days  
 Use 250D High Low to define Fibo Top and Bottom Lines  
 If stay below 0.382 for more than {2} days, THEN EXIT

S12. EFFECTIVE after {240} Days  
 Use 250D High Low to define Fibo Top and Bottom Lines  
 If stay below 0.236 for more than {22} days, THEN EXIT

S13. Effective after {238} Days  
 Exit if close below {80} day closing low

S14. Effective after {300} days, if price underperforming HSI for {35} and 2\*{35} and 3\*{35} days, then Exit

S15. If price decline is more than {25%} within {4} days, then EXIT

S16. If Current ATR(22) rose more than {50%} in the past {12} days.  
 AND if price decline is more than {15%} within 10 days, then EXIT

S17. Effective after {150} days  
 IF ({150-day High} / {150-Day low} \- 1\) \* 100 \> {60%}  
 THEN EXIT if ({close} / {150-Day low} \- 1\) \* 100 \< {60%} / 2

**Energy Level**

E1. New high in the past {20D} and close is higher than \[Low \+ {0.65} \* (High \- Low)  
E2. StochRSI(10) \> 0.5  
E3. SLOPE(Close, {66}) \> 0  
E4. Price change over 33 days outperforming 2800  
E5. Latest price is at top half of 5-day range and current price \> price of 5 days ago and current price is less than 7% drawdown from 250D high
