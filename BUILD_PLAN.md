# Build Plan

## Objective

Identify diagnostic orders likely to miss their promised turnaround at the
interim checkpoint and prepare proactive, review-gated patient notifications.

## Delivered

- Explainable checkpoint-time breach risk score.
- React command center with ranked queue, alert review, Trigger Lab, and delivery setup.
- Timestamp-derived checkpoint scoring and a local patient-text inbox with phone preview.
- FastAPI risk and queue endpoints.
- Consent-checked notification drafts requiring staff approval.
- Automated SMTP operations alerts with deduplication and continuous watcher.
- Held-out and June 1-13 evaluation.

## Measured results

Official held-out set, June 2-13:

- Orders: 17,450
- ROC-AUC: 0.953
- Recall: 91.27%
- Precision: 72.12%
- Existing checkpoint-rule recall: 83.11%

Complete June 1-13 period:

- Orders: 19,250
- ROC-AUC: 0.953
- Recall: 91.37%
- Precision: 72.01%

## Production continuation

1. Validate fields and performance on approved hospital data.
2. Replace final daily resource statistics with real-time signals.
3. Calibrate the threshold with diagnostics operations.
4. Integrate with LIS/HIS events and approved messaging.
5. Add authentication, audit logging, monitoring, and a silent pilot.
