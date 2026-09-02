import numpy as np
from sklearn.mixture import GaussianMixture
import logging


class RegimeDetector:
    def __init__(self, n_regimes=3):
        self.n_regimes = n_regimes
        self.model = GaussianMixture(n_components=n_regimes, random_state=42, n_init=5)

    def classify(self, df):
        try:
            close = df['Close'].tail(100)
            returns = np.log(close / close.shift(1)).fillna(0)
            volatility = returns.rolling(window=10).std().fillna(0)
            features = np.column_stack([returns, volatility])
            self.model.fit(features)
            labels = self.model.predict(features)
            current_label = labels[-1]
            cluster_vols = []
            for i in range(self.n_regimes):
                subset = features[labels == i, 1]
                cluster_vols.append(subset.mean() if len(subset) else float('inf'))
            rank = np.argsort(cluster_vols)
            if current_label == rank[0]:
                return 0
            if current_label == rank[1]:
                return 1
            return 2
        except Exception as exc:
            logging.error(f"Regime Detection Error: {exc}")
            return 0
