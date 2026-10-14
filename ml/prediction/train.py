"""M2 training pipeline (phases 5-12), runnable end to end.

    python -m prediction.train extract-osm      # phase 3: OSM -> road stats (once per OSM snapshot)
    python -m prediction.train train            # phases 5-12: panel, models, SHAP, MLflow, bundle
    python -m prediction.train ablation         # phase 11: feature-group ablation on the chosen model
    python -m prediction.train all              # everything above

Run from the `ml/` directory (or with ml/ on PYTHONPATH).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .config import SPLITS, REPORT_DIR, PROCESSED_DIR, RAW_DIR, ensure_dirs
from .evaluation import (best_f1_threshold, calibration_table, classification_metrics,
                         per_group_metrics, regression_metrics)
from .explain import global_importance, save_beeswarm, save_importance_plot
from .features import build_training_panel, temporal_split
from .io_accidents import load_accidents
from .io_osm import ROAD_CLASSES, extract_osm, load_road_stats
from .io_weather import load_weather
from .models import CLASSIFIER_GRIDS, fit_classifier, fit_regressor, REGRESSOR_FACTORY
from .registry import ModelBundle, PlattCalibrator, save_bundle
from .tracking import start_run

# A tree model replaces the transparent baseline only if it is clearly better.
MIN_PR_AUC_GAIN = 0.005


def _sha256(path: Path, limit_mb: int = 512) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load_inputs():
    acc = load_accidents()
    wx = load_weather()
    rs = load_road_stats()
    return acc, wx, rs


def road_class_weights(acc_train: pd.DataFrame, roads_stats: pd.DataFrame) -> dict[str, float]:
    """Relative accident rate per km by road class (training period only).

    weight_c = share of geolocated-by-class accidents on class c / share of OSM km of class c,
    normalised so the km-weighted mean weight is 1. Accidents whose place text gives no
    class ('unknown', 'road_other') are excluded from the shares.
    """
    known = acc_train[acc_train["road_class"].isin(ROAD_CLASSES)]
    acc_share = known["road_class"].value_counts(normalize=True).reindex(ROAD_CLASSES, fill_value=0)
    km = roads_stats[[f"road_km_{c}" for c in ROAD_CLASSES]].sum()
    km.index = ROAD_CLASSES
    km_share = km / km.sum()
    w = (acc_share / km_share).replace([np.inf, np.nan], 1.0)
    w = w / (w * km_share).sum()
    return {k: round(float(v), 4) for k, v in w.items()}


def _select(results: dict) -> str:
    base = results["logreg"]["val"]["pr_auc"]
    best = max(results, key=lambda k: results[k]["val"]["pr_auc"])
    if best != "logreg" and results[best]["val"]["pr_auc"] - base < MIN_PR_AUC_GAIN:
        return "logreg"
    return best


def train(args) -> ModelBundle:
    ensure_dirs()
    t0 = time.time()
    acc, wx, rs = load_inputs()
    panel, fs = build_training_panel(acc, wx, rs, start=SPLITS.panel_start, end=SPLITS.test_end)
    panel.to_parquet(PROCESSED_DIR / "panel_governorate_day.parquet", index=False)
    tr, va, te = temporal_split(panel, SPLITS.train_end, SPLITS.val_end, SPLITS.test_end)
    X = fs.all
    print(f"[panel] {len(panel):,} rows | train {len(tr):,} | val {len(va):,} | test {len(te):,} | {len(X)} features")

    version = time.strftime("%Y.%m.%d-%H%M")
    data_meta = {
        "accidents_rows": int(len(acc)), "accidents_first": str(acc["date"].min().date()),
        "accidents_last": str(acc["date"].max().date()),
        "weather_first": str(wx["date"].min().date()), "weather_last": str(wx["date"].max().date()),
        "panel_rows": int(len(panel)), "panel_start": str(panel["date"].min().date()),
        "panel_end": str(panel["date"].max().date()),
        "split": {"train_end": SPLITS.train_end, "val_end": SPLITS.val_end, "test_end": str(te["date"].max().date())},
        "sources": {p.name: _sha256(p) for p in (RAW_DIR / config.ACCIDENTS_FILE, RAW_DIR / config.WEATHER_FILE) if p.exists()},
    }

    report: dict = {"version": version, "data": data_meta, "classification": {}, "regression": {}, "fatal": {}}
    with start_run(f"m2-train-{version}", use_mlflow=not args.no_mlflow) as run:
        run.set_tags({"work_package": "M2", "mode": "A", "granularity": "governorate-day"})
        run.log_params({"n_features": len(X), "train_end": SPLITS.train_end, "val_end": SPLITS.val_end,
                        "panel_start": SPLITS.panel_start, "python": platform.python_version()})

        # ---------------- phases 7-9: accident_flag classifiers with small grids
        results, fitted = {}, {}
        for name, grid in CLASSIFIER_GRIDS.items():
            best = None
            for params in grid:
                m = fit_classifier(name, params, tr[X], tr["accident_flag"], va[X], va["accident_flag"])
                p_va = m.predict_proba(va[X])[:, 1]
                pr = classification_metrics(va["accident_flag"], p_va, 0.5)["pr_auc"]
                if best is None or pr > best[0]:
                    best = (pr, params, m, p_va)
            _, params, m, p_va = best
            thr = best_f1_threshold(va["accident_flag"], p_va)
            p_te = m.predict_proba(te[X])[:, 1]
            results[name] = {"params": params,
                             "val": classification_metrics(va["accident_flag"], p_va, thr),
                             "test": classification_metrics(te["accident_flag"], p_te, thr)}
            fitted[name] = m
            run.log_metrics(results[name]["val"], prefix=f"{name}.val.")
            run.log_metrics(results[name]["test"], prefix=f"{name}.test.")
            print(f"[{name}] params={params} val PR-AUC={results[name]['val']['pr_auc']:.4f} "
                  f"test PR-AUC={results[name]['test']['pr_auc']:.4f} ROC={results[name]['test']['roc_auc']:.4f} "
                  f"F1={results[name]['test']['f1']:.4f}@{thr}")
        report["classification"]["candidates"] = results

        chosen = _select(results)
        clf = fitted[chosen]
        # Calibration on validation (Platt, rank-preserving); threshold re-chosen on calibrated validation scores
        p_va_base = clf.predict_proba(va[X])[:, 1]
        cal = PlattCalibrator().fit(p_va_base, va["accident_flag"])
        p_va = cal.predict(p_va_base)
        thr = best_f1_threshold(va["accident_flag"], p_va)
        p_te = cal.predict(clf.predict_proba(te[X])[:, 1])
        final_test = classification_metrics(te["accident_flag"], p_te, thr)
        report["classification"]["chosen"] = chosen
        report["classification"]["final_calibrated_test"] = final_test
        run.log_metrics(final_test, prefix="final.test.")
        print(f"[chosen] {chosen} (calibrated) test: {json.dumps({k: round(v, 4) for k, v in final_test.items()})}")

        # Naive reference: yesterday-had-accident / 30-day rate as a score
        naive = (te["hist_acc_sum_30"] / 30).fillna(0).clip(0, 1)
        report["classification"]["naive_rate30_test"] = classification_metrics(
            te["accident_flag"], naive, best_f1_threshold(va["accident_flag"], (va["hist_acc_sum_30"] / 30).fillna(0).clip(0, 1)))

        te_eval = te[["gov_code", "date", "accident_flag"]].assign(p=p_te)
        per_gov = per_group_metrics(te_eval, "accident_flag", "p")
        per_gov.to_csv(REPORT_DIR / "test_metrics_per_governorate.csv", index=False)
        calibration_table(te["accident_flag"], p_te).to_csv(REPORT_DIR / "test_calibration.csv", index=False)

        # ---------------- count regression
        reg_results, reg_fitted = {}, {}
        for name in REGRESSOR_FACTORY:
            m = fit_regressor(name, tr[X], tr["accident_count"], va[X], va["accident_count"])
            reg_results[name] = {"val": regression_metrics(va["accident_count"], m.predict(va[X])),
                                 "test": regression_metrics(te["accident_count"], m.predict(te[X]))}
            reg_fitted[name] = m
            run.log_metrics(reg_results[name]["test"], prefix=f"count.{name}.test.")
            print(f"[count:{name}] test MAE={reg_results[name]['test']['mae']:.4f} "
                  f"RMSE={reg_results[name]['test']['rmse']:.4f} R2={reg_results[name]['test']['r2']:.4f}")
        candidates = {k: v for k, v in reg_results.items() if k != "naive_rolling_mean"}
        count_name = min(candidates, key=lambda k: candidates[k]["val"]["poisson_deviance"])
        report["regression"] = {"candidates": reg_results, "chosen": count_name}

        # ---------------- fatal-accident classifier (rare event, reported with PR-AUC)
        fat = fit_classifier(chosen, results[chosen]["params"], tr[X], tr["fatal_flag"], va[X], va["fatal_flag"])
        pf_va_base = fat.predict_proba(va[X])[:, 1]
        fcal = PlattCalibrator().fit(pf_va_base, va["fatal_flag"])
        pf_te = fcal.predict(fat.predict_proba(te[X])[:, 1])
        fthr = best_f1_threshold(va["fatal_flag"], fcal.predict(pf_va_base))
        report["fatal"] = {"model": chosen, "test": classification_metrics(te["fatal_flag"], pf_te, fthr)}
        run.log_metrics(report["fatal"]["test"], prefix="fatal.test.")
        print(f"[fatal] test PR-AUC={report['fatal']['test']['pr_auc']:.4f} (base rate {report['fatal']['test']['base_rate']:.3f})")

        # ---------------- phase 10: explainability on the test period
        imp = global_importance(clf, te[X])
        imp.to_csv(REPORT_DIR / "feature_importance.csv", index=False)
        run.log_artifact(save_importance_plot(imp, REPORT_DIR / "feature_importance.png",
                                              f"M2 {chosen} — global contribution (test)"))
        bee = save_beeswarm(clf, te[X], REPORT_DIR / "shap_beeswarm.png")
        if bee:
            run.log_artifact(bee)
        for f in ("test_metrics_per_governorate.csv", "test_calibration.csv", "feature_importance.csv"):
            run.log_artifact(REPORT_DIR / f)

        weights = road_class_weights(acc[acc["date"] <= SPLITS.train_end], rs)
        report["road_class_weights"] = weights
        report["elapsed_s"] = round(time.time() - t0, 1)

        bundle = ModelBundle(
            version=version, features=X, feature_groups=fs.groups(),
            classifier=clf, classifier_name=chosen, calibrator=cal, threshold=thr,
            count_model=reg_fitted[count_name], count_model_name=count_name,
            fatal_classifier=fat, fatal_calibrator=fcal, road_class_weights=weights,
            metrics={"accident_flag_test": final_test, "count_test": reg_results[count_name]["test"],
                     "fatal_test": report["fatal"]["test"]},
            metadata={**data_meta, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "risk_levels": vars(config.RISK_LEVELS), "contract_version": config.CONTRACT_VERSION},
            mlflow_run_id=run.id if run.backend == "mlflow" else None,
        )
        path = save_bundle(bundle)
        report["bundle"] = str(path.name)
        report["mlflow_run_id"] = bundle.mlflow_run_id
        (REPORT_DIR / "training_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        run.log_artifact(REPORT_DIR / "training_report.json")
        print(f"[bundle] saved {path} ({path.stat().st_size / 1e6:.1f} MB) in {report['elapsed_s']} s")
    return bundle


def ablation(args) -> pd.DataFrame:
    """Phase 11: retrain the chosen model family without each feature group."""
    from .registry import load_bundle
    ensure_dirs()
    bundle = load_bundle()
    acc, wx, rs = load_inputs()
    panel, fs = build_training_panel(acc, wx, rs, start=SPLITS.panel_start, end=SPLITS.test_end)
    tr, va, te = temporal_split(panel, SPLITS.train_end, SPLITS.val_end, SPLITS.test_end)
    params = json.loads((REPORT_DIR / "training_report.json").read_text())["classification"]["candidates"][bundle.classifier_name]["params"]
    rows = []
    variants = {"all": fs.all, **{f"without_{g}": [c for c in fs.all if c not in cols] for g, cols in fs.groups().items()},
                **{f"only_{g}": cols for g, cols in fs.groups().items()}}
    with start_run(f"m2-ablation-{bundle.version}", use_mlflow=not args.no_mlflow) as run:
        for name, cols in variants.items():
            m = fit_classifier(bundle.classifier_name, params, tr[cols], tr["accident_flag"], va[cols], va["accident_flag"])
            p_va = m.predict_proba(va[cols])[:, 1]
            thr = best_f1_threshold(va["accident_flag"], p_va)
            met = classification_metrics(te["accident_flag"], m.predict_proba(te[cols])[:, 1], thr)
            rows.append({"variant": name, "n_features": len(cols), **{k: met[k] for k in ("roc_auc", "pr_auc", "f1", "brier")}})
            run.log_metrics({k: met[k] for k in ("roc_auc", "pr_auc", "f1")}, prefix=f"{name}.")
            print(f"[ablation] {name:<20} PR-AUC={met['pr_auc']:.4f} ROC-AUC={met['roc_auc']:.4f}")
        out = pd.DataFrame(rows)
        ref = out.loc[out["variant"] == "all", "pr_auc"].iloc[0]
        out["delta_pr_auc_vs_all"] = out["pr_auc"] - ref
        out.to_csv(REPORT_DIR / "ablation.csv", index=False)
        run.log_artifact(REPORT_DIR / "ablation.csv")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="M2 risk-prediction training pipeline")
    ap.add_argument("command", choices=["extract-osm", "train", "ablation", "all"])
    ap.add_argument("--no-mlflow", action="store_true", help="log runs as JSON only")
    args = ap.parse_args(argv)
    if args.command in ("extract-osm", "all"):
        if args.command == "all" and (PROCESSED_DIR / "governorate_road_stats.csv").exists():
            print("[osm] road stats already present, skipping extraction")
        else:
            g, r = extract_osm()
            print(f"[osm] {len(g)} governorates, {len(r):,} road ways")
    if args.command in ("train", "all"):
        train(args)
    if args.command in ("ablation", "all"):
        ablation(args)
    if args.command in ("train", "ablation", "all"):
        from .report import main as card
        card([])


if __name__ == "__main__":
    main()
