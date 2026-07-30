"""Frozen forecast layer: regularised logistic regression, P(critical at t+2h).
critical = <=2 bikes or <=2 free docks. Trained ONCE on clean data; tau calibrated
once on clean validation data, then FROZEN across all corruption experiments."""
from sklearn.linear_model import LogisticRegression


def train_frozen_model(X, y):
    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(X, y)
    return model


def predict_critical(model, X):
    return model.predict_proba(X)[:, 1]


def demo():
    import numpy as np

    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 3))
    y = (X[:, 0] + rng.normal(scale=0.1, size=500) > 0).astype(int)
    model = train_frozen_model(X, y)
    proba = predict_critical(model, X)
    assert proba.shape == (500,)
    assert ((proba >= 0.5).astype(int) == y).mean() > 0.9  # separable toy data
    print("model.demo: OK")


if __name__ == "__main__":
    demo()
