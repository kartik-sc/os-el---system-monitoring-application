# ml/feature_engineering.py
"""
Feature engineering for anomaly detection models.
Transforms raw time-series into features suitable for ML.
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """Extract features from time-series windows"""
    
    @staticmethod
    def extract_features(values: list, metric_key: str = "unknown") -> dict:
        """
        Extract statistical + temporal features from metric window.
        
        Args:
            values: list of recent metric values (from StreamProcessor.get_window)
            metric_key: name of metric (for context)
        
        Returns:
            dict of features ready for ML models
        """
        if len(values) < 5:
            return None
        
        values = np.array(values, dtype=float)
        
        # Statistical features
        mean = float(np.mean(values))
        std = float(np.std(values))
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        median = float(np.median(values))
        
        # Handle zero std
        if std < 1e-6:
            std = 1e-6
        
        # Trend features
        delta = float(values[-1] - values[0])  # overall trend
        latest = float(values[-1])
        prev = float(values[-2]) if len(values) > 1 else latest
        recent_change = latest - prev
        
        # Volatility
        diffs = np.diff(values)
        volatility = float(np.std(diffs)) if len(diffs) > 0 else 0.0
        
        # Z-score of latest
        z_score = float((latest - mean) / std) if std > 1e-6 else 0.0
        
        # Rolling entropy (change rate)
        if len(values) > 3:
            rolling_ratio = []
            for i in range(1, len(values)):
                if values[i-1] != 0:
                    ratio = abs((values[i] - values[i-1]) / values[i-1])
                    rolling_ratio.append(ratio)
            entropy = float(np.mean(rolling_ratio)) if rolling_ratio else 0.0
        else:
            entropy = 0.0
        
        # Skewness (peak detection)
        q75 = float(np.percentile(values, 75))
        q25 = float(np.percentile(values, 25))
        iqr = q75 - q25
        
        # Multivariate feature vector (for autoencoder)
        feature_vec = [
            latest, mean, std, min_val, max_val, median,
            z_score, delta, volatility, entropy, iqr, recent_change
        ]
        
        return {
            'latest': latest,
            'mean': mean,
            'std': std,
            'min': min_val,
            'max': max_val,
            'median': median,
            'z_score': z_score,
            'trend': delta,
            'volatility': volatility,
            'entropy': entropy,
            'iqr': iqr,
            'recent_change': recent_change,
            'feature_vector': feature_vec,  # For autoencoder
            'raw_values': values.tolist(),
        }