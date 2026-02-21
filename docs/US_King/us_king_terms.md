US Algo (King) 2025  
\=================

## Buy Rule

**Buy if {\[B1 AND B8\] OR \[B18\]} AND B9 AND B10 AND B11 AND B12 AND B13 AND B20 AND B21 and B22**

B1. \[  
 CLOSE ABOVE Bollinger Band (22, 0.89) but not deviating from {50MA} by {25%}  
 \]  
 AND  
 \[  
 close is higher than \[Low \+ {RATIO} \* (High \- Low)\]  
 \]

B8. {85D} low \> T-{86D} to T-{150D} low

B9. CANCEL Buy if Close \< (Last {105D} High \+ Last {105D} Low) /2 and high Date is earlier than low date

B10. if 250D low happens within {68} days before breakout, cancel buy

B11. IF Current ATR(22) is higher than {67%} of maximum ATR(22) in the past {215} day, THEN cancel buy.

B12. If 150D SMA has risen {16%} in the past {50} days AND Today high is deviating from 150DMA by 20%, THEN CANCEL Buy

B13. CANCEL buy if the stock is underperforming SPY for {19}-Day AND {100}-Day look back periods.

B18. Mark Minervini's Volatility Contraction Pattern (VCP) Detection \- Criteria for Breakout Setup  
 B18(1) The current price is below the {252D} high but above {60%} of {252D} high.  
 B18(2) The 50D SMA of volume has a negative linear regression slope over the past {50D} periods.  
 B18(3) ({5D} high - {5D} low)/close is less than {0.1} AND {5D} high occurred {5D} ago.
B18(4) Each of the last {5D} volume below its own {50D} volume SMA (volume[i] \< 50SMA_volume[i] for i=0 to 4).

B20. Total up day volume more than total down day volume in the past {20} days and the highest volume in the past {20} days is the highest or the second highest volume in the past {20} days.

B21. R3 \= 3M high \- 3M low  
 R1 \= 1M high \- 1M low  
 Only release buy signal if R3 is at least {1.09} bigger than R1  
 AND Price is less than {4.2%} below 3 month high

B22. Cancel buy if hard stop cannot be found at the low-{2.45}\*ATR(10) of the highest volume UP day (with low-{2.45}\*ATR(10) \< buy close price) in past {41} days ({41} same as S19's {41})

## Stop Rule

**Stop if \[S1 OR S4 OR S5 OR S6 OR S7 OR S8 OR S9 OR S10 OR S11 OR S12 OR S13 OR S14 OR S15 OR S16 OR S17 OR S18 OR S19 OR S20\]**

S1. Use \[CLOSE \- {3.4}\*ATR({22})\] as stop position, if stop loss is \> {20%}, set stop loss at {7.2%} instead of close of \[CLOSE \- {3.4}\*ATR({22})\].

S4. Enable this rule on the {50}th trading day after issuing Buy.  
 Let A \= counting number of trading day whereas Daily Close \> 50D MA in the past {50} days.  
 If A/{50} \< {45%} and {50} Days gain is \< {7%} then exit trade

S5. Effective on or after {50} days  
 Initial stop \= entry price \+ {0.7}\*ATR(20)  
 Push up stop by {0.7}\*ATR(10) every {30} days.

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

S14. Effective after {300} days, if price underperforming SPY for {65} and 2\*{65} and 3\*{65} days, then Exit

S15. If price decline is more than {25%} within {4} days, then EXIT

S16. If Current ATR(22) rose more than {50%} in the past {12} days.  
 AND if price decline is more than {14%} within 10 days, then EXIT

S17. Effective after {150} days  
 IF ({150-day High} / {150-Day low} \- 1\) \* 100 \> {60%}  
 THEN EXIT if ({close} / {150-Day low} \- 1\) \* 100 \< {60%} / 2  
S18. If close below {120} days low then exit  
 Only valid for first {20} days

S19. Set hard stop at low-{2.45}\*ATR(10) of the highest volume UP day (with low-{2.45}\*ATR(10) \< buy close price) in past {41} days

S20. ATR \= \[ATR(100)+ATR(20)+ATR(5)\]/3  
 If price drops \[{5.4} x ATR\] within {5} days, Exit

## Energy Level

E1. New high in the past {20D} and close is higher than \[Low \+ {0.65} \* (High \- Low)  
E2. StochRSI(10) \> 0.5  
E3. SLOPE(Close, {66}) \> 0  
E4. Price change over 33 days outperforming SPY  
E5. Latest price is at top half of 5-day range and current price \> price of 5 days ago and current price is less than 7% drawdown from 250D high
