# ml/arima_model.py
"""
ARIMA-like trend prediction for time-series forecasting.
Simplified differencing + AutoRegression (no external ARIMA lib dependency).
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class SimpleARIMA:
    """
    Simplified ARIMA using differencing + AR.
    No statsmodels dependency (keeps it lightweight).
    """
    
    def __init__(self, order=(1, 1, 0)):
        """
        order: (p, d, q)
        - p: AR order
        - d: differencing order
        - q: MA order (simplified, not used)
        """
        self.p, self.d, self.q = order
        self.ar_coefs = None
        self.fitted = False
    
    def fit(self, timeseries: list):
        """
        Fit AR model on differenced series.
        timeseries: list of values
        """
        if len(timeseries) < self.p + self.d + 5:
            return
        
        ts = np.array(timeseries, dtype=float)
        
        # Differencing
        for _ in range(self.d):
            ts = np.diff(ts)
        
        # Simple AR: fit AR(p) on differenced series
        if len(ts) > self.p:
            X = np.array([ts[i:i+self.p] for i in range(len(ts)-self.p)])
            y = ts[self.p:]
            
            # Least squares AR fit
            try:
                self.ar_coefs = np.linalg.lstsq(X, y, rcond=None)[0]
                self.fitted = True
            except:
                pass
    
    def forecast(self, timeseries: list, steps: int = 1) -> list:
        """Forecast next steps"""
        if not self.fitted or len(timeseries) < self.p:
            return timeseries[-1:] * steps
        
        ts = np.array(timeseries, dtype=float)
        
        # Difference
        for _ in range(self.d):
            ts = np.diff(ts)
        
        forecasts = []
        for _ in range(steps):
            if len(ts) >= self.p:
                last_p = ts[-self.p:]
                next_val = np.dot(self.ar_coefs, last_p)
                forecasts.append(next_val)
                ts = np.append(ts, next_val)
        
        return forecasts if forecasts else [timeseries[-1]]