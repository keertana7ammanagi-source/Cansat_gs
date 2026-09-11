"""
Offline training script for AI models.
Generates synthetic data, trains models, and saves them to models/ folder.
"""
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib

os.makedirs("models", exist_ok=True)

# --- Generate synthetic flight data ---
def generate_flight_data(num_packets=500):
    data = {
        'ALTITUDE': [], 'PRESSURE': [], 'TEMP': [], 'HUMIDITY': [],
        'UV_INDEX': [], 'LIGHT_INTENSITY': [], 'TIME': []
    }
    for t in range(num_packets):
        alt = 1000 * (1 - np.cos(t * np.pi / 60)) if t < 30 else 1000 - 20 * (t - 30)
        if alt < 0: alt = 0
        press = 1013.25 * np.exp(-alt / 8500)
        temp = 25 - 0.0065 * alt + np.random.normal(0, 0.5)
        hum = 40 + np.random.normal(0, 5)
        uv = 3 + np.random.normal(0, 0.5)
        light = 200 * (1 - alt/1200) + np.random.normal(0, 10)
        data['ALTITUDE'].append(alt)
        data['PRESSURE'].append(press)
        data['TEMP'].append(temp)
        data['HUMIDITY'].append(hum)
        data['UV_INDEX'].append(uv)
        data['LIGHT_INTENSITY'].append(light)
        data['TIME'].append(t)
    return pd.DataFrame(data)

df = generate_flight_data(500)

# --- Train Environmental Fingerprint (K-Means) ---
features = df[['PRESSURE', 'TEMP', 'HUMIDITY', 'UV_INDEX', 'LIGHT_INTENSITY', 'ALTITUDE']].values
scaler = StandardScaler()
X_scaled = scaler.fit_transform(features)
kmeans = KMeans(n_clusters=3, random_state=42)
kmeans.fit(X_scaled)
joblib.dump(scaler, 'models/fingerprint_scaler.pkl')
joblib.dump(kmeans, 'models/fingerprint_kmeans.pkl')
print("Fingerprint model saved.")

# --- Train Trend Predictor (Random Forest) ---
X, y = [], []
for i in range(10, len(df)-1):
    X.append(df[['PRESSURE', 'TEMP', 'HUMIDITY', 'ALTITUDE']].iloc[i-10:i].values.flatten())
    y.append(df['PRESSURE'].iloc[i+1])
X = np.array(X)
y = np.array(y)
rf_press = RandomForestRegressor(n_estimators=100, random_state=42)
rf_press.fit(X, y)
joblib.dump(rf_press, 'models/trend_press_rf.pkl')
print("Trend predictor model saved.")

print("All models trained and saved to models/ folder.")