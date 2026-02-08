# ml/trend_prediction.py
"""
Trend prediction using ARIMA + Linear Regression ensemble.
Forecasts next values to detect unusual trajectories.
"""

import asyncio
import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from sklearn.linear_model import LinearRegression
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from ml.arima_model import SimpleARIMA


class TrendPredictor:
    """Ensemble forecaster: ARIMA + Linear Regression"""
    
    def __init__(self):
        self.arima_models = {}  # per metric_key
        self.lr_models = {}  # per metric_key
        self.fitted_metrics = set()
    
    def _ensure_models(self, metric_key: str, values: list):
        """Initialize forecasting models"""
        if metric_key in self.fitted_metrics or len(values) < 15:
            return
        
        # ARIMA
        try:
            arima = SimpleARIMA(order=(2, 1, 0))
            arima.fit(values)
            if arima.fitted:
                self.arima_models[metric_key] = arima
        except Exception as e:
            logger.debug(f"ARIMA fit failed for {metric_key}: {e}")
        
        # Linear Regression
        if HAS_SKLEARN:
            try:
                X = np.arange(len(values)).reshape(-1, 1)
                y = np.array(values)
                lr = LinearRegression()
                lr.fit(X, y)
                self.lr_models[metric_key] = lr
            except Exception as e:
                logger.debug(f"Linear regression fit failed: {e}")
        
        self.fitted_metrics.add(metric_key)
    
    def forecast(self, metric_key: str, values: list, steps: int = 3) -> dict:
        """
        Forecast next values.
        
        Returns:
            {
                'forecast': [list of predicted values],
                'method': 'ensemble',
                'confidence': float,
            }
        """
        if len(values) < 10:
            return {'forecast': [], 'method': 'insufficient', 'confidence': 0.0}
        
        self._ensure_models(metric_key, values)
        
        forecasts = {}
        
        # ARIMA forecast
        if metric_key in self.arima_models:
            try:
                fc = self.arima_models[metric_key].forecast(values, steps=steps)
                forecasts['arima'] = fc
            except:
                pass
        
        # Linear Regression forecast
        if metric_key in self.lr_models:
            try:
                lr = self.lr_models[metric_key]
                X_future = np.arange(len(values), len(values) + steps).reshape(-1, 1)
                fc = lr.predict(X_future).tolist()
                forecasts['linear'] = fc
            except:
                pass
        
        # Ensemble average
        if forecasts:
            ensemble_fc = np.mean(list(forecasts.values()), axis=0).tolist()
            return {
                'forecast': ensemble_fc,
                'method': 'ensemble',
                'confidence': float(len(forecasts) / 2.0),
            }
        
        return {'forecast': [], 'method': 'none', 'confidence': 0.0}


class TrendPredictionPipeline:
    """Async pipeline for trend anomalies"""
    
    def __init__(self, stream_processor, enable: bool = True):
        self.stream_processor = stream_processor
        self.enable = enable
        self.running = False
        self.predictor = TrendPredictor()
    
    async def start(self):
        logger.info("TrendPredictionPipeline started")
        self.running = True
        if not self.enable:
            logger.info("Trend prediction disabled")
            return
        
        try:
            while self.running:
                await self._predict_trends()
                await asyncio.sleep(30.0)  # Less frequent than anomaly detection
        except asyncio.CancelledError:
            logger.info("TrendPredictionPipeline cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _predict_trends(self):
        """Check if trends are anomalous"""
        if not self.enable:
            return
        
        try:
            metrics = self.stream_processor.get_metric_keys()
            for metric_key in metrics[:5]:  # Limit to top 5 to save compute
                values = self.stream_processor.get_window(metric_key, seconds=600)
                if len(values) < 20:
                    continue
                
                result = self.predictor.forecast(metric_key, values, steps=5)
                
                # Log forecast (no event for now, just tracking)
                logger.debug(f"{metric_key} trend: {result}")
        
        except Exception as e:
            logger.error(f"Error in trend prediction: {e}", exc_info=True)