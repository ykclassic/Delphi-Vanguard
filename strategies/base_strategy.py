from abc import ABC, abstractmethod


class BaseStrategy(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def generate_signal(self, df, regime):
        """Return 'BUY', 'SELL', or None in the Oracle baseline contract."""
        raise NotImplementedError
