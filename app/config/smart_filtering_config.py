import os


SMART_FILTERING_ENABLED = os.getenv('SMART_FILTERING_ENABLED', 'true').lower() == 'true'
MIN_PAYOFF_RATIO = float(os.getenv('MIN_PAYOFF_RATIO', '2'))
OUT_PAYOFF_RATIO = float(os.getenv('OUT_PAYOFF_RATIO', '1'))
MIN_OBSERVATIONS = int(os.getenv('MIN_OBSERVATIONS', '2'))
