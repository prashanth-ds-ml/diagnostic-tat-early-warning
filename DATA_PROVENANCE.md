# Data Provenance

The CSV files bundled in this repository are synthetic challenge data copied
from:

`https://github.com/nallamotu/yashoda-synthetic-buildlab`

They are not real Yashoda Hospital patient data.

## Included files

| File | Purpose |
|---|---|
| `synthetic_diagnostic_orders.csv` | Diagnostic checkpoint inputs and outcomes |
| `synthetic_diagnostic_resources.csv` | Daily resource capacity and downtime context |
| `synthetic_op_patients.csv` | Patient notification-consent gate |
| `synthetic_diagnostic_orders_test_labels.csv` | Held-out Problem 9 evaluation labels |

Only checkpoint-time fields are used for live risk scoring. Outcome fields
and held-out labels are used solely for offline evaluation.

The application can use another approved data directory by setting:

```bash
export DIAGNOSTIC_DATA_DIR=/path/to/data
```
