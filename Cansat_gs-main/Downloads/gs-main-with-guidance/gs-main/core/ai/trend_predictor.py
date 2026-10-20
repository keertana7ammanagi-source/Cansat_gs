"""
Atmospheric Trend Predictor – Random Forest regression to predict pressure, temp, humidity.
Loads a pre-trained model if available; otherwise trains online.
"""
import os
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

from utils.logger import get_logger

logger = get_logger(__name__)


class AtmosphericTrendPredictor:
    """
    Predicts pressure, temperature, and humidity 1 step ahead (1 second)
    using a window of the last 10 samples.
    """

    def __init__(self, window_size=10):
        self.window_size = window_size
        self.history = []          # list of (press, temp, hum, alt)
        self.models = {}
        self.trained = False
        self.prediction = None
        self._load_or_init_models()

    def _load_or_init_models(self):
        """
        Attempt to load pre-trained Random Forest models.
        """
        model_path = "models/trend_press_rf.pkl"
        if os.path.exists(model_path):
            try:
                # We can load a single model for pressure, or separate ones for temp/hum
                # For simplicity, we load the pressure model; temp/hum will be trained online.
                # In a full implementation, you'd load all three.
                self.models['press'] = joblib.load(model_path)
                self.trained = True
                logger.info("Loaded pre-trained trend model (pressure).")
                # For temp and hum, we'll train online
                self.models['temp'] = RandomForestRegressor(n_estimators=50)
                self.models['hum'] = RandomForestRegressor(n_estimators=50)
            except Exception as e:
                logger.warning(f"Failed to load pre-trained model: {e}. Falling back to online training.")
                self._init_models()
        else:
            logger.info("No pre-trained trend model found. Will train online.")
            self._init_models()

    def _init_models(self):
        """Initialize fresh models for online training."""
        self.models = {
            'press': RandomForestRegressor(n_estimators=50),
            'temp': RandomForestRegressor(n_estimators=50),
            'hum': RandomForestRegressor(n_estimators=50),
        }
        self.trained = False

    def add_sample(self, packet):
        """
        Add a new telemetry sample to the history.
        If enough samples are accumulated, train the models.
        """
        press = packet.get("PRESSURE", 0)
        temp = packet.get("TEMP", 0)
        hum = packet.get("HUMIDITY", 0)
        alt = packet.get("ALTITUDE", 0)

        # Skip invalid samples
        if any(v == 0 for v in [press, temp, hum, alt]) or press is None:
            return

        self.history.append((press, temp, hum, alt))

        # If we have enough samples, train
        if len(self.history) >= (self.window_size + 10) and not self.trained:
            self._train_online()

    def _train_online(self):
        """Train the models on the accumulated history."""
        if len(self.history) < self.window_size + 2:
            return

        X = []      # features: flattened window of (press, temp, hum, alt) for last 10 steps
        y_press = []
        y_temp = []
        y_hum = []

        for i in range(self.window_size, len(self.history) - 1):
            # Use the last 'window_size' samples to predict the next one
            window = self.history[i - self.window_size:i]
            # Flatten: [p1,t1,h1,a1, p2,t2,h2,a2, ...]
            flat = []
            for p, t, h, a in window:
                flat.extend([p, t, h, a])
            X.append(flat)
            # Target is the next sample
            next_p, next_t, next_h, _ = self.history[i]
            y_press.append(next_p)
            y_temp.append(next_t)
            y_hum.append(next_h)

        if len(X) > 0:
            X = np.array(X)
            self.models['press'].fit(X, y_press)
            self.models['temp'].fit(X, y_temp)
            self.models['hum'].fit(X, y_hum)
            self.trained = True
            logger.info("Trend models trained online.")

    def predict(self, current_press, current_temp, current_hum, current_alt):
        """
        Predict the next values for pressure, temperature, humidity.
        Uses the last 'window_size' samples from history.
        Returns a dict with predictions and change detection.
        """
        # If not enough history or not trained, return None
        if not self.trained or len(self.history) < self.window_size:
            return None

        # Build the feature vector from the last 'window_size' samples
        window = self.history[-self.window_size:]
        flat = []
        for p, t, h, a in window:
            flat.extend([p, t, h, a])
        X_input = np.array([flat])

        try:
            pred_press = self.models['press'].predict(X_input)[0]
            pred_temp = self.models['temp'].predict(X_input)[0]
            pred_hum = self.models['hum'].predict(X_input)[0]

            # Detect significant change (sudden pressure drop, temp spike, etc.)
            change = False
            if len(self.history) > 1:
                last = self.history[-1]
                if abs(pred_press - last[0]) > 5 or abs(pred_temp - last[1]) > 2 or abs(pred_hum - last[2]) > 10:
                    change = True

            self.prediction = {
                "predicted_pressure": pred_press,
                "predicted_temperature": pred_temp,
                "predicted_humidity": pred_hum,
                "change_detected": change,
            }
            return self.prediction
        except Exception as e:
            logger.warning(f"Prediction failed: {e}")
            return None

    def reset(self):
        """Clear history and reset training."""
        self.history = []
        self.trained = False
        self.prediction = None
        self._init_models()