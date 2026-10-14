"""Kept for backward compatibility — the M2 models live in models.py / train.py."""
from .models import xgboost_clf


def train_xgb(X_train, y_train, X_val, y_val, **params):
    model = xgboost_clf(**params)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    return model
