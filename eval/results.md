### Headline: S4 small + harness vs S1 baseline (combined test + hand-written)

| Metric | S1 baseline | Best | Gain |
|---|---|---|---|
| Execution accuracy (answer items) | 90.7% | 95.0% | +4.3 pts |
| Behavior accuracy (clarify/refuse) | 92.0% | 92.0% | +0.0 pts |
| Cost per 1k tickets (USD) | 0.4674 | 0.523 | +0.056 |
| p50 latency (ms) | 3143 | 3240 | +97 |

Accuracy gap +4.3 pts, 95% cluster-bootstrap CI [+1.1, +7.9], McNemar p = 0.0015 (22 items only S4 got right vs 5 only S1 got right) -> **real gain**.

### All setups

| Setup | Test acc | Hand-written acc | Combined acc | Seen tmpl | Unseen tmpl | Behavior | p50 ms | $/1k tickets | vs S1 (combined) |
|---|---|---|---|---|---|---|---|---|---|
| S0 small, schema only | 51.1% | 50.0% | 51.0% | 45.1% | 60.7% | 92.0% | 3867 | 0.383 | -39.6 pts, p=0.000, real loss |
| S1 baseline (small + dictionary) | 91.3% | 83.3% | 90.7% | 88.1% | 96.4% | 92.0% | 3143 | 0.467 | baseline |
| S2 Nemotron Ultra | 83.1% | 80.0% | 82.8% | 76.1% | 94.3% | 98.0% | 7499 | 2.597 | -7.8 pts, p=0.000, real loss |
| S4 small + harness | 95.4% | 90.0% | 95.0% | 92.9% | 99.3% | 92.0% | 3240 | 0.523 | +4.3 pts, p=0.002, real gain |
| S6 router (S4 -> Ultra) | 94.5% | 90.0% | 94.2% | 91.2% | 100.0% | 90.0% | 3069 | 0.542 | +3.5 pts, p=0.009, real gain |

### Accuracy by category (combined)

| Setup | simple | join | date | business_rule | gotcha | clarify | refuse |
|---|---|---|---|---|---|---|---|
| S0 | 93.1% | 90.7% | 27.9% | 12.8% | 75.7% | 84.0% | 100.0% |
| S1 | 91.4% | 81.4% | 97.7% | 92.6% | 88.3% | 84.0% | 100.0% |
| S2 | 84.5% | 72.1% | 86.0% | 85.2% | 81.6% | 96.0% | 100.0% |
| S4 | 96.6% | 88.4% | 95.3% | 96.6% | 94.2% | 84.0% | 100.0% |
| S6 | 98.3% | 83.7% | 97.7% | 96.6% | 91.3% | 80.0% | 100.0% |
