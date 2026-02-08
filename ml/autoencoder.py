# ml/autoencoder.py
"""
Simple autoencoder for multivariate anomaly detection.
No LSTM, pure feedforward (efficient + fast).
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    from sklearn.neural_network import MLPRegressor
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


class SimpleAutoencoder:
    """Lightweight feedforward autoencoder"""
    
    def __init__(self, input_dim: int = 12, hidden_dim: int = 6):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.encoder = None
        self.decoder = None
        self.threshold = 0.5
        self.fitted = False
        
        if HAS_SKLEARN:
            # Encoder: input -> hidden
            self.encoder = MLPRegressor(
                hidden_layer_sizes=(hidden_dim,),
                activation='relu',
                max_iter=100,
                random_state=42,
                warm_start=True
            )
            # Decoder: hidden -> input reconstruction
            self.decoder = MLPRegressor(
                hidden_layer_sizes=(hidden_dim,),
                activation='relu',
                max_iter=100,
                random_state=42,
                warm_start=True
            )
    
    def fit(self, X: np.ndarray):
        """
        Train autoencoder on normal data.
        X: shape (n_samples, input_dim)
        """
        if not HAS_SKLEARN or X.shape[0] < 10:
            return
        
        try:
            # Simple bottleneck training
            self.encoder.fit(X, X[:, :self.hidden_dim])
            self.decoder.fit(X[:, :self.hidden_dim], X)
            
            # Compute reconstruction errors on training data for threshold
            errors = self._compute_errors(X)
            self.threshold = float(np.percentile(errors, 95))  # 95th percentile
            self.fitted = True
            logger.debug(f"Autoencoder trained. Threshold: {self.threshold:.4f}")
        except Exception as e:
            logger.debug(f"Autoencoder fit failed: {e}")
    
    def _compute_errors(self, X: np.ndarray) -> np.ndarray:
        """Compute reconstruction error for each sample"""
        try:
            encoded = self.encoder.predict(X)
            reconstructed = self.decoder.predict(encoded)
            errors = np.mean(np.abs(X - reconstructed), axis=1)
            return errors
        except:
            return np.zeros(X.shape[0])
    
    def predict(self, x: np.ndarray) -> int:
        """
        Predict if sample is anomalous.
        Returns: 1 if anomaly, 0 if normal
        """
        if not self.fitted or not HAS_SKLEARN:
            return 0
        
        try:
            x_reshaped = x.reshape(1, -1)
            error = self._compute_errors(x_reshaped)[0]
            return 1 if error > self.threshold else 0
        except:
            return 0
    
    def predict_score(self, x: np.ndarray) -> float:
        """Return anomaly score (reconstruction error)"""
        if not self.fitted or not HAS_SKLEARN:
            return 0.0
        
        try:
            x_reshaped = x.reshape(1, -1)
            error = self._compute_errors(x_reshaped)[0]
            return float(error)
        except:
            return 0.0