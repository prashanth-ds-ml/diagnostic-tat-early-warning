from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from risk_engine import DATA_DIR, score_dataframe


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"


def auc(y_true: pd.Series, scores: pd.Series) -> float:
    positives = int(y_true.sum())
    negatives = len(y_true) - positives
    ranks = scores.rank(method="average")
    return float((ranks[y_true.eq(1)].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def classification_metrics(y_true: pd.Series, predicted: pd.Series) -> dict[str, float | int]:
    tp = int(((predicted == 1) & (y_true == 1)).sum())
    fp = int(((predicted == 1) & (y_true == 0)).sum())
    fn = int(((predicted == 0) & (y_true == 1)).sum())
    tn = int(((predicted == 0) & (y_true == 0)).sum())
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "recall": tp / (tp + fn),
        "precision": tp / (tp + fp),
    }


def main() -> None:
    orders = pd.read_csv(DATA_DIR / "synthetic_diagnostic_orders.csv")
    labels = pd.read_csv(DATA_DIR / "synthetic_diagnostic_orders_test_labels.csv")
    test = orders[orders["order_id"].isin(labels["order_id"])].copy()
    test = test.merge(labels, on="order_id", how="inner")
    scored = score_dataframe(test)
    scores = test[["order_id", "on_track_at_checkpoint"]].merge(scored, on="order_id")
    y_true = test.set_index("order_id").loc[scores["order_id"], "true_value"].astype(int).reset_index(drop=True)

    model_pred = scores["breach_probability"].ge(0.40).astype(int)
    rule_pred = (~scores["on_track_at_checkpoint"].astype(bool)).astype(int)
    result = {
        "test_orders": len(scores),
        "breach_rate": float(y_true.mean()),
        "current_retroactive_warning_recall": 0.0,
        "model_auc": auc(y_true, scores["breach_probability"]),
        "model_threshold": 0.40,
        "model": classification_metrics(y_true, model_pred),
        "checkpoint_rule": classification_metrics(y_true, rule_pred),
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    scores[["order_id", "breach_probability", "risk_level"]].to_csv(
        OUTPUT_DIR / "test_predictions.csv", index=False
    )
    (OUTPUT_DIR / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
