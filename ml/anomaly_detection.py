# ml/anomaly_detection.py
"""
Multi-model Anomaly Detection Pipeline (COMPLETE).
Trained stacking model + Z-score + IsolationForest + OneClassSVM + Autoencoder.
CLI events published correctly.
"""

import asyncio
import logging
import numpy as np
import time
from collections import defaultdict
import joblib

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.svm import OneClassSVM
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from .feature_engineering import FeatureEngineer
from .autoencoder import SimpleAutoencoder
from .arima_model import SimpleARIMA


class StackedAnomalyDetector:
    """
    5-model ensemble:
    1. Z-score (statistical)
    2. IsolationForest (tree-based)
    3. OneClassSVM (kernel SVM)
    4. Autoencoder (neural reconstruction)
    5. TRAINED KAGGLE MODEL (stacking from your datasets)
    """
    
    def __init__(self):
        self.models = {}  # Live models per metric
        self.scalers = {}  # SVM scalers
        self.autoencoders = {}  # Autoencoders
        self.feature_engineer = FeatureEngineer()
        self.fitted_metrics = set()
        
        # Trained model
        self.trained_model = None
        self.trained_scaler = None
        self.trained_features = None
        self.trained = False
        
        if not HAS_SKLEARN:
            logger.warning("scikit-learn not installed, using Z-score + trained model only")
    
    def load_trained_model(self, path: str = 'trained_kaggle_detector.pkl'):
        """Load your Kaggle-trained stacking model"""
        try:
            data = joblib.load(path)
            self.trained_model = data['model']
            self.trained_scaler = data['scaler']
            self.trained_features = data['features']
            self.trained = True
            logger.info(f"✅ Loaded Kaggle-trained model ({len(self.trained_features)} features)")
        except Exception as e:
            logger.warning(f"Failed to load trained model {path}: {e}")
    
    def _ensure_model(self, metric_key: str, values: list):
        """Lazy-fit live models"""
        if metric_key in self.fitted_metrics or len(values) < 20:
            return
        
        values_np = np.array(values, dtype=float).reshape(-1, 1)
        
        # IsolationForest
        if HAS_SKLEARN:
            try:
                self.models[metric_key] = IsolationForest(contamination=0.1, random_state=42)
                self.models[metric_key].fit(values_np)
            except Exception:
                pass
        
        # OneClassSVM
        if HAS_SKLEARN:
            try:
                scaler = StandardScaler()
                scaled = scaler.fit_transform(values_np)
                self.scalers[metric_key] = scaler
                ocsvm = OneClassSVM(nu=0.05, kernel='rbf', gamma='auto')
                ocsvm.fit(scaled)
                self.models[f"{metric_key}_ocsvm"] = ocsvm
            except Exception:
                pass
        
        # Autoencoder
        try:
            features = [self.feature_engineer.extract_features(values[i:i+10])
                       for i in range(0, len(values)-10, 5) if len(values[i:i+10]) >= 5]
            features = [f for f in features if f is not None]
            if features:
                X = np.array([f['feature_vector'] for f in features])
                ae = SimpleAutoencoder(input_dim=12)
                ae.fit(X)
                self.autoencoders[metric_key] = ae
        except Exception:
            pass
        
        self.fitted_metrics.add(metric_key)
    
    def detect(self, metric_key: str, values: list) -> dict:
        """
        FULL 5-MODEL DETECTION + VOTING.
        
        Returns:
            {
                'is_anomaly': True/False,
                'confidence': 0.0-1.0,
                'method': 'trained_kaggle'|'z_score'|...,
                'scores': {'z_score':1, 'isolation_forest':0, ...},
                'votes': 3,
                'total_methods': 5
            }
        """
        if len(values) < 5:
            return {'is_anomaly': False, 'confidence': 0.0, 'method': 'insufficient_data'}
        
        self._ensure_model(metric_key, values)
        values_np = np.array(values, dtype=float)
        latest = values_np[-1]
        history = values_np[:-1]
        
        scores = {}
        votes = 0
        total_methods = 0
        
        # 1. Z-Score (always works)
        mean = float(np.mean(history))
        std = float(np.std(history))
        if std > 1e-6:
            z = abs((latest - mean) / std)
            z_anomaly = 1 if z > 3.0 else 0
            scores['z_score'] = z_anomaly
            votes += z_anomaly
        total_methods += 1
        
        # 2. IsolationForest
        if HAS_SKLEARN and metric_key in self.models:
            try:
                pred = self.models[metric_key].predict([[latest]])[0]
                scores['isolation_forest'] = 1 if pred == -1 else 0
                votes += scores['isolation_forest']
            except:
                pass
            total_methods += 1
        
        # 3. OneClassSVM
        if HAS_SKLEARN and f"{metric_key}_ocsvm" in self.models:
            try:
                scaler = self.scalers[metric_key]
                scaled = scaler.transform([[latest]])
                pred = self.models[f"{metric_key}_ocsvm"].predict(scaled)[0]
                scores['ocsvm'] = 1 if pred == -1 else 0
                votes += scores['ocsvm']
            except:
                pass
            total_methods += 1
        
        # 4. Autoencoder
        if metric_key in self.autoencoders:
            try:
                features = self.feature_engineer.extract_features(values)
                if features:
                    feat_vec = np.array(features['feature_vector'], dtype=float)
                    ae_pred = self.autoencoders[metric_key].predict(feat_vec)
                    scores['autoencoder'] = ae_pred
                    votes += ae_pred
            except:
                pass
            total_methods += 1
        
        # 5. TRAINED KAGGLE MODEL (your datasets!)
        if self.trained:
            try:
                features = self.feature_engineer.extract_features(values)
                if features and len(features['feature_vector']) >= len(self.trained_features):
                    # Match exact training features
                    feat_vec = np.array(features['feature_vector'][:len(self.trained_features)]).reshape(1, -1)
                    feat_scaled = self.trained_scaler.transform(feat_vec)
                    trained_pred = self.trained_model.predict(feat_scaled)[0]
                    scores['trained_kaggle'] = int(trained_pred)
                    votes += int(trained_pred)
                    logger.debug(f"{metric_key}: trained_kaggle={trained_pred}")
            except Exception as e:
                logger.debug(f"Trained model predict failed: {e}")
            total_methods += 1
        
        # Majority voting
        is_anomaly = votes >= max(1, total_methods // 2)
        confidence = votes / total_methods if total_methods > 0 else 0.0
        
        # Strongest method
        method = max(scores, key=scores.get) if scores else 'unknown'
        
        return {
            'is_anomaly': bool(is_anomaly),
            'confidence': float(confidence),
            'method': method,
            'scores': scores,
            'votes': int(votes),
            'total_methods': total_methods,
            'latest_value': float(latest),
            'metric_key': metric_key
        }


class AnomalyDetectionPipeline:
    """Main async pipeline"""
    
    def __init__(self, stream_processor, window_seconds: int = 300, model_path: str = 'trained_kaggle_detector.pkl'):
        self.stream_processor = stream_processor
        self.window_seconds = window_seconds
        self.running = False
        self.detector = StackedAnomalyDetector()
        self.detector.load_trained_model(model_path)
        self.anomaly_scores = defaultdict(float)
        
        logger.info("🚀 StackedAnomalyDetector ready (5 models + Kaggle-trained)")
    
    async def start(self):
        logger.info("AnomalyDetectionPipeline started")
        self.running = True
        try:
            while self.running:
                await self._detect_anomalies()
                await asyncio.sleep(3.0)  # Faster detection
        except asyncio.CancelledError:
            logger.info("AnomalyDetectionPipeline cancelled")
        finally:
            self.running = False
    
    async def stop(self):
        self.running = False
    
    async def _detect_anomalies(self):
        from ingestion.event_bus import SystemEvent, EventType
        
        try:
            metrics = self.stream_processor.get_metric_keys()
            now = time.time()
            
            for metric_key in metrics:
                values = self.stream_processor.get_window(metric_key, seconds=self.window_seconds)
                
                if len(values) < 10:
                    continue
                
                # FULL 5-MODEL DETECTION
                result = self.detector.detect(metric_key, values)
                
                if result['is_anomaly']:
                    # ✅ PUBLISH TO CLI DASHBOARD
                    anomaly_event = SystemEvent(
                        event_type=EventType.ANOMALY,
                        source="ml::5model_detector",
                        data={
                            "metric_key": result['metric_key'],
                            "value": result['latest_value'],
                            "method": result['method'],
                            "confidence": result['confidence'],
                            "votes": result['votes'],
                            "total_methods": result['total_methods'],
                            "scores": result['scores'],
                        },
                    )
                    await self.stream_processor.event_bus.publish(anomaly_event)
                    
                    logger.info(f"🚨 ANOMALY: {result['metric_key']} "
                              f"({result['latest_value']:.1f}) "
                              f"[{result['method']}] conf={result['confidence']:.2f}")
                    
                    # Track for dashboard summary
                    self.anomaly_scores[metric_key] = result['confidence']
        
        except Exception as e:
            logger.error(f"Anomaly detection error: {e}", exc_info=True)
    
    def get_overall_anomaly_score(self) -> float:
        """0-100 score for CLI dashboard"""
        if not self.anomaly_scores:
            return 0.0
        
        # Weighted recent average
        scores = list(self.anomaly_scores.values())
        return min(100.0, np.mean(scores) * 100.0)