"""Kept for backward compatibility — the M2 models live in models.py / train.py."""
from .models import logreg


def train_baseline(X_train, y_train):
    return logreg().fit(X_train, y_train)
