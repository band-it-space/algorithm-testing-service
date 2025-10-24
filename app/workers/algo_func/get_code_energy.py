from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class StockRecord:
    """Stock price record"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int

def process_stock_data(stock_data: List[StockRecord], load_data_date: datetime) -> Dict[str, Any]:
    """Process stock data and return arrays for calculation"""
    ldate = []
    lsdate = []
    lopen = []
    lhigh = []
    llow = []
    lclose = []
    lvolume = []
    
    min_date = datetime(2001, 1, 1)
    
    for record in stock_data:
        if not record.date or record.date.strip() == "":
            continue
            
        try:
            record_date = datetime.strptime(record.date, "%Y-%m-%d")
            
            if record_date < load_data_date or record_date < min_date:
                continue
            
            ldate.append(record_date)
            lsdate.append(record.date)
            lopen.append(record.open)
            lhigh.append(record.high)
            llow.append(record.low)
            lclose.append(record.close)
            lvolume.append(record.volume)
            
        except ValueError:
            # Skip invalid date formats
            continue
    
    return {
        'dates': ldate,
        'string_dates': lsdate,
        'open': lopen,
        'high': lhigh,
        'low': llow,
        'close': lclose,
        'volume': lvolume
    }

def calculate_rsi(prices: List[float], current_idx: int, period: int) -> List[float]:
    """Calculate RSI values"""
    if current_idx < period:
        return [float('nan')] * (current_idx + 1)

    price_data = prices[:current_idx + 1]
    rsi_values = [float('nan')] * len(price_data)  # Initialize with NaN

    # Calculate price changes
    deltas = []
    for i in range(1, len(price_data)):
        deltas.append(price_data[i] - price_data[i-1])
    
    if len(deltas) < period:
        return rsi_values
    
    # Separate gains and losses
    gains = [max(delta, 0) for delta in deltas]
    losses = [abs(min(delta, 0)) for delta in deltas]
    
    # Calculate initial average (first period using SMA)
    initial_avg_gain = sum(gains[:period]) / period
    initial_avg_loss = sum(losses[:period]) / period
    
    # Calculate first RSI at index 'period'
    if initial_avg_loss == 0:
        rsi = 100.0
    else:
        rs = initial_avg_gain / initial_avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    
    rsi_values[period] = rsi  # First valid RSI at index 'period'
    
    # Continue with Wilder's Smoothing
    avg_gain = initial_avg_gain
    avg_loss = initial_avg_loss
    
    for i in range(period, len(deltas)):  # Start from period, not period+1
        # Wilder's Smoothing
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        
        rsi_values[i + 1] = rsi  # RSI for price at index i+1
    
    return rsi_values

def calculate_energy_indicators_last_16_days(trade_day: str, stock_data: List[StockRecord], stock_data_2800: List[StockRecord]) -> Dict[str, Any]:
    """
    Calculate E1-E5 energy indicators for the last 16 trading days including the current day
    
    Args:
        stockname: Stock code/name
        trade_day: Trade date in format 'YYYY-MM-DD' (current/target date)
        stock_data: List of stock price records
        stock_data_2800: List of reference index (2800) price records
        
    Returns:
        Dictionary with E1-E5 indicators for the last 16 trading days
    """
    try:
        in_date = datetime.strptime(trade_day, "%Y-%m-%d")
        load_data_date = in_date - relativedelta(months=24)
        
        processed_data = process_stock_data(stock_data, load_data_date)
        processed_data_spy = process_stock_data(stock_data_2800, load_data_date)
        
        close = processed_data['close']
        high = processed_data['high']
        low = processed_data['low']
        ddate = processed_data['dates']
        sdate = processed_data['string_dates']
        
        # SPY (reference data) arrays
        close_spy = processed_data_spy['close']
        sdate_spy = processed_data_spy['string_dates']
        
        # Find the last 16 trading days including the target date
        target_dates = []
        target_indices = []
        
        # Find the index of the target date
        target_idx = -1
        for i, date in enumerate(ddate):
            if date <= in_date:
                target_idx = i
        
        if target_idx == -1:
            return {
                "status": "error",
                "message": f"Target date {trade_day} not found in data",
                "indicators": []
            }
        
        # Get the last 16 indices (including target date)
        start_idx = max(0, target_idx - 15)  # 15 days before + target date = 16 days
        for i in range(start_idx, target_idx + 1):
            target_dates.append(ddate[i])
            target_indices.append(i)
        
        all_indicators = []
        
        for idx in target_indices:
            # islatest - mark as latest if it's the target date (last in our 16-day range)
            is_latest = "1" if idx == target_idx else "0"
            
            if idx >= 66:  # with at least 66 bars for calculation
                
                #####################################
                # E1. New high in the past {20D} and close is higher than [Low + {0.65} * (High - Low)]
                # high > highest(high, 20)[1] and
                # close > (high - low) * 0.65 + low
                
                # Calculate max high in the past 20 days (not including current bar)
                start_idx = max(0, idx - 20)
                end_idx = idx - 1  # not including current bar
                
                if end_idx >= start_idx:
                    max_high_20d = max(high[start_idx:end_idx + 1])
                else:
                    max_high_20d = 0
                
                # Check E1 conditions
                if (high[idx] > max_high_20d and 
                    close[idx] > (high[idx] - low[idx]) * 0.65 + low[idx]):
                    E1 = "1"
                else:
                    E1 = "0"
                
                #####################################
                # E2. StochRSI(10) > 0.5
                period_rsi = 10
                period_stoch = 10
                
                if idx >= (period_rsi + period_stoch - 1):
                    rsi_values = calculate_rsi(close, idx, period_rsi)
                
                    rsi_val = rsi_values[idx]
                
                    start_pos = idx - (period_stoch - 1)
                    end_pos = idx + 1
                
                    window = [v for v in rsi_values[start_pos:end_pos] if not (v != v)]
                    if len(window) == period_stoch:
                        max_val = max(window)
                        min_val = min(window)
                        if max_val == min_val:
                            stochrsi = 0.0
                        else:
                            stochrsi = (rsi_val - min_val) / (max_val - min_val)
                        E2 = "1" if stochrsi > 0.5 else "0"
                    else:
                        E2 = "0"
                else:
                    E2 = "0"

                #####################################
                # E3. SLOPE(Close, {66}) > 0
                # (close - close[66])/66
                if (close[idx] - close[idx - 66]) / 66 > 0:
                    E3 = "1"
                else:
                    E3 = "0"

                #####################################
                # E4. Price change over 33 days outperforming SPY
                # close/close[33] > close data(2)/close[33] data(2)
                
                # Find matching date in SPY data
                try:
                    arr_idx = sdate_spy.index(sdate[idx])
                    
                    # Check if we have enough data (33 days back) for both stock and SPY
                    if (idx >= 33 and arr_idx >= 33 and 
                        arr_idx < len(close_spy) and idx < len(close)):
                        
                        stock_performance = close[idx] / close[idx - 33]
                        spy_performance = close_spy[arr_idx] / close_spy[arr_idx - 33]
                        
                        if stock_performance > spy_performance:
                            E4 = "1"
                        else:
                            E4 = "0"
                    else:
                        E4 = "0" 
                        
                except ValueError:
                    E4 = "0"
                
                #####################################
                # E5. Latest price is at top half of 5-day range and current price > price of 5 days ago 
                # and current price is less than 7% drawdown from 66D high
                # (close - lowest(low, 5))/(highest(high, 5) - lowest(low, 5)) > 0.5
                # close - close[5] > 0
                # (highest(high, 66) - close)/highest(high, 66) < 0.07
                
                # lowest(low, 5) - get min low of last 5 days including current
                start_idx_5 = max(0, idx - 4)  # Last 5 days including current
                min5 = min(low[start_idx_5:idx + 1])
                    
                # highest(high, 5) - get max high of last 5 days including current
                max5 = max(high[start_idx_5:idx + 1])
                    
                # lowest(low, 250) - get min low of last 250 days including current
                start_idx_250 = max(0, idx - 249)  # Last 250 days including current
                    
                # highest(high, 250) - get max high of last 250 days including current
                max250 = max(high[start_idx_250:idx + 1])
                    
                # Check all three E5 conditions
                condition1 = (close[idx] - min5) / (max5 - min5) > 0.5 if max5 != min5 else False
                condition2 = close[idx] - close[idx - 5] > 0 if idx >= 5 else False
                condition3 = (max250 - close[idx]) / max250 < 0.07 if max250 != 0 else False
                    
                if condition1 and condition2 and condition3:
                    E5 = "1"
                else:
                    E5 = "0"
                    
            else:
                E1 = "N/A"
                E2 = "N/A"
                E3 = "N/A"
                E4 = "N/A"
                E5 = "N/A"
            
            # Store indicators for this record (we're already processing only the 16 days we want)
            all_indicators.append({
                "date": sdate[idx],
                "E1": E1,
                "E2": E2,
                "E3": E3,
                "E4": E4,
                "E5": E5,
                "is_latest": is_latest
            })
        
        # Calculate sum of all E1-E5 values divided by 80
        total_energy_sum = 0
        valid_count = 0
        
        for indicator in all_indicators:
            for energy_key in ["E1", "E2", "E3", "E4", "E5"]:
                energy_value = indicator[energy_key]
                if energy_value == "1":
                    total_energy_sum += 1
                elif energy_value == "0":
                    total_energy_sum += 0
                # Skip "N/A" values
                
                # Count valid values (not "N/A")
                if energy_value in ["0", "1"]:
                    valid_count += 1
        
        energy_score = total_energy_sum / 16 if valid_count > 0 else 0
        
        return {
            "energy_score": energy_score,
            "E1": all_indicators[-1]['E1'],
            "E2": all_indicators[-1]['E2'],
            "E3": all_indicators[-1]['E3'],
            "E4": all_indicators[-1]['E4'],
            "E5": all_indicators[-1]['E5'],
        }

        # return {
        #     "status": "success",
        #     "message": f"Energy indicators calculated for {stockname} - last {len(all_indicators)} trading days",
        #     "total_days": len(all_indicators),
        #     "energy_sum": total_energy_sum,
        #     "energy_score": energy_score,
        #     "valid_indicators_count": valid_count,
        #     "indicators": all_indicators
        # }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error calculating energy indicators: {str(e)}",
            "indicators": []
        }

def calculate_energy_indicators_single_day(stockname: str, trade_day: str, stock_data: List[StockRecord], stock_data_2800: List[StockRecord]) -> Dict[str, Any]:
    """
    Calculate E1-E5 energy indicators for a single day (original function)
    
    Args:
        stockname: Stock code/name
        trade_day: Trade date in format 'YYYY-MM-DD'
        stock_data: List of stock price records
        stock_data_2800: List of reference index (2800) price records
        
    Returns:
        Dictionary with E1-E5 indicators for the specified date
    """
    # Call the 16-day function and return only the last day
    result = calculate_energy_indicators_last_16_days(stockname, trade_day, stock_data, stock_data_2800)
    
    if result["status"] == "success" and result["indicators"]:
        # Return only the last day (target date)
        last_day_indicator = result["indicators"][-1]
        return {
            "status": "success",
            "message": f"Energy indicators calculated for {stockname} on {trade_day}",
            "indicators": [last_day_indicator]
        }
    else:
        return result