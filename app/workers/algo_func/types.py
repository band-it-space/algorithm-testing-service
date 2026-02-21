from dataclasses import dataclass
from typing import Optional

@dataclass
class OHLCV:
    """Open, High, Low, Close, Volume data structure for price bars."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
