from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime

class UnifiedTradeSignal(BaseModel):
    buy_signal: datetime
    stop_signal: Union[datetime, str]  
    entry_price: float
    exit_price: Union[float, str]  
    day_before_buy: Optional[datetime] = None
    day_before_sell: Optional[datetime] = None
    gain_lose: Optional[float] = None  
    source: str  