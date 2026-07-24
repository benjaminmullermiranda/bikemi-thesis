"""Frozen forecast layer: regularised logistic regression, P(critical at t+2h).
critical = <=2 bikes or <=2 free docks. Trained ONCE on clean data; tau calibrated
once on clean validation data, then FROZEN across all corruption experiments."""

def train_frozen_model(X, y):
    raise NotImplementedError

def predict_critical(model, X):
    raise NotImplementedError
