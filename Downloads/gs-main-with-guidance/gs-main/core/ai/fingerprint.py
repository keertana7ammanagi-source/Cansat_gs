"""
Environmental Fingerprint Engine – K-Means clustering on atmospheric data.
Loads pre-trained scaler and KMeans if available, otherwise trains online.
"""
import os
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib

from utils.logger import get_logger

logger = get_logger(__name__)


class EnvironmentalFingerprintEngine:
    """
    Classifies atmospheric conditions (Clear, Cloudy, Hazy, High UV, etc.)
    using K-Means clustering on pressure, temperature, humidity, UV, light, altitude.
    """

    def __init__(self, n_clusters=3):
        self.samples = []
        self.classified = False
        self.class_label = None
        self.scaler = None
        self.kmeans = None
        self.n_clusters = n_clusters
        self._load_or_init_models()

    def _load_or_init_models(self):
        """
        Attempt to load pre-trained scaler and KMeans from models/ folder.
        If not found, initialize new ones for online training.
        """
        model_dir = "models"
        scaler_path = os.path.join(model_dir, "fingerprint_scaler.pkl")
        kmeans_path = os.path.join(model_dir, "fingerprint_kmeans.pkl")

        if os.path.exists(scaler_path) and os.path.exists(kmeans_path):
            try:
                self.scaler = joblib.load(scaler_path)
                self.kmeans = joblib.load(kmeans_path)
                self.classified = True  # We can classify immediately
                logger.info("Loaded pre-trained fingerprint models.")
            except Exception as e:
                logger.warning(f"Failed to load pre-trained models: {e}. Falling back to online training.")
                self.scaler = StandardScaler()
                self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=42)
                self.classified = False
        else:
            logger.info("No pre-trained fingerprint models found. Will train online.")
            self.scaler = StandardScaler()
            self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=42)
            self.classified = False

    def update(self, packet):
        """
        Process a new telemetry packet.
        If classified, directly predict the label using the loaded model.
        Otherwise, accumulate samples and train when enough data (≥50).
        """
        # Extract features from the packet
        features = [
            packet.get("PRESSURE", 0),
            packet.get("TEMP", 0),
            packet.get("HUMIDITY", 0),
            packet.get("UV_INDEX", 0),
            packet.get("LIGHT_INTENSITY", 0),
            packet.get("ALTITUDE", 0),
        ]

        # If any sensor value is missing or zero, skip (but still return current label)
        if all(v == 0 for v in features):
            return {"classified": self.classified, "class_label": self.class_label}

        self.samples.append(features)

        # If we already have a trained model, just predict
        if self.classified and self.scaler is not None and self.kmeans is not None:
            try:
                # Scale the features using the loaded scaler
                scaled = self.scaler.transform([features])
                label = self.kmeans.predict(scaled)[0]
                self.class_label = self._label_to_string(label)
                return {"classified": True, "class_label": self.class_label}
            except Exception as e:
                logger.warning(f"Prediction failed: {e}. Reverting to online training.")
                self.classified = False

        # Online training mode: accumulate samples and train when enough
        if len(self.samples) >= 50 and not self.classified:
            try:
                X = np.array(self.samples)
                X_scaled = self.scaler.fit_transform(X)
                self.kmeans.fit(X_scaled)
                self.classified = True
                label = self.kmeans.predict([X_scaled[-1]])[0]
                self.class_label = self._label_to_string(label)
                logger.info("Fingerprint model trained online.")
            except Exception as e:
                logger.error(f"Online training failed: {e}")

        # Return current status
        return {"classified": self.classified, "class_label": self.class_label}

    def _label_to_string(self, label):
        """
        Convert numeric label to human-readable string.
        Customize as needed based on your dataset.
        """
        # Common atmospheric types – you can adjust labels based on your training data
        labels = {
            0: "Clear Sky",
            1: "Cloudy",
            2: "Hazy",
        }
        # If we have more clusters, add more
        if label not in labels:
            return f"Type {chr(65+label)}"  # A, B, C, ...
        return labels.get(label, f"Type {label}")

    def reset(self):
        """Clear all samples and reset classification."""
        self.samples = []
        self.classified = False
        self.class_label = None