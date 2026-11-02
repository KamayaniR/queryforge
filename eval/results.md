### Headline: GLM 5.3 Flash fine-tuned (S5) vs S1 baseline (combined test + hand-written)

| Metric | S1 baseline | Best | Gain |
|---|---|---|---|
| Execution accuracy (answer items) | 90.7% | 96.7% | +6.0 pts |
| Behavior accuracy (clarify/refuse) | 92.0% | 100.0% | +8.0 pts |
| Cost per 1k tickets (USD) | 0.4674 | 0.2907 | -0.177 |
| p50 latency (ms) | 3143 | 4008 | +865 |

Accuracy gap +6.0 pts, 95% cluster-bootstrap CI [+1.8, +11.0], McNemar p = 0.0001 (31 items only S5 got right vs 7 only S1 got right) -> **real gain**.

### All setups

| Setup | Items run (test / hw) | Test acc | Hand-written acc | Combined acc | Seen tmpl | Unseen tmpl | Behavior | p50 ms | $/1k tickets | vs S1, paired on same answer items |
|---|---|---|---|---|---|---|---|---|---|---|
| GLM 5.3 Flash, schema only (S0) | 416 / 30 | 51.1% | 50.0% | 51.0% | 45.1% | 60.7% | 92.0% | 3867 | 0.383 | -39.7 pts, p=0.000, real loss (n=396) |
| GLM 5.3 Flash + dictionary, baseline (S1) | 416 / 30 | 91.3% | 83.3% | 90.7% | 88.1% | 96.4% | 92.0% | 3143 | 0.467 | baseline |
| Nemotron 3 Ultra + dictionary (S2) | 416 / 30 | 83.1% | 80.0% | 82.8% | 76.1% | 94.3% | 98.0% | 7499 | 2.597 | -7.9 pts, p=0.000, real loss (n=396) |
| GLM 5.3 Flash + harness (S4) | 416 / 30 | 95.4% | 90.0% | 94.9% | 92.9% | 99.3% | 92.0% | 3240 | 0.523 | +4.2 pts, p=0.002, real gain (n=396) |
| GLM 5.3 Flash fine-tuned (S5) | 416 / 30 | 98.9% | 70.0% | 96.7% | 98.7% | 99.3% | 100.0% | 4008 | 0.291 | +6.0 pts, p=0.000, real gain (n=396) |
| GLM 5.3 Flash fine-tuned + harness (S5H) | 0 / 30 | - | 73.3% | 73.3% | - | - | - | 46611 | 0.393 | -10.0 pts, p=0.375, could be luck (n=30) |
| GLM 5.3 Flash + harness → Nemotron 3 Ultra (S6) | 416 / 30 | 94.5% | 90.0% | 94.2% | 91.2% | 100.0% | 90.0% | 3069 | 0.542 | +3.5 pts, p=0.009, real gain (n=396) |

### Paired vs S1 on the same items (S1 acc → setup acc (gap; only-setup-right/only-S1-right; McNemar p; verdict) n)

| Setup | Seen templates | Held-out templates | Hand-written | Behavior (clarify/refuse) |
|---|---|---|---|---|
| GLM 5.3 Flash, schema only (S0) | 88.1 → 45.1 (-43.0; 12/109; p=9.87e-21; real loss) n=226 | 96.4 → 60.7 (-35.7; 1/51; p=2.35e-14; real loss) n=140 | 83.3 → 50.0 (-33.3; 0/10; p=0.00195; real loss) n=30 | 92.0 → 92.0 (+0.0; 1/1; p=1; could be luck) n=50 |
| Nemotron 3 Ultra + dictionary (S2) | 88.1 → 76.1 (-12.0; 10/37; p=9.85e-05; real loss) n=226 | 96.4 → 94.3 (-2.1; 2/5; p=0.453; could be luck) n=140 | 83.3 → 80.0 (-3.3; 1/2; p=1; could be luck) n=30 | 92.0 → 98.0 (+6.0; 3/0; p=0.25; could be luck) n=50 |
| GLM 5.3 Flash + harness (S4) | 88.1 → 92.9 (+4.8; 16/5; p=0.0266; real gain) n=226 | 96.4 → 99.3 (+2.9; 4/0; p=0.125; could be luck) n=140 | 83.3 → 90.0 (+6.7; 2/0; p=0.5; could be luck) n=30 | 92.0 → 92.0 (+0.0; 0/0; p=1; could be luck) n=50 |
| GLM 5.3 Flash fine-tuned (S5) | 88.1 → 98.7 (+10.6; 25/1; p=8.05e-07; real gain) n=226 | 96.4 → 99.3 (+2.9; 5/1; p=0.219; could be luck) n=140 | 83.3 → 70.0 (-13.3; 1/5; p=0.219; could be luck) n=30 | 92.0 → 100.0 (+8.0; 4/0; p=0.125; could be luck) n=50 |
| GLM 5.3 Flash fine-tuned + harness (S5H) | - | - | 83.3 → 73.3 (-10.0; 1/4; p=0.375; could be luck) n=30 | - |
| GLM 5.3 Flash + harness → Nemotron 3 Ultra (S6) | 88.1 → 91.2 (+3.1; 13/6; p=0.167; could be luck) n=226 | 96.4 → 100.0 (+3.6; 5/0; p=0.0625; could be luck) n=140 | 83.3 → 90.0 (+6.7; 2/0; p=0.5; could be luck) n=30 | 92.0 → 90.0 (-2.0; 0/1; p=1; could be luck) n=50 |

### S4 vs S2 (Nemotron Ultra), paired (S2 acc → S4 acc)

| Slice | Result |
|---|---|
| Answer items, test + hand-written | 82.8 → 94.9 (+12.1; 53/5; p=3.5e-11; real gain) n=396 |
| Hand-written only | 80.0 → 90.0 (+10.0; 3/0; p=0.25; could be luck) n=30 |
| Behavior (clarify/refuse) | 98.0 → 92.0 (-6.0; 0/3; p=0.25; could be luck) n=50 |

### Accuracy by category (combined)

| Setup | simple | join | date | business_rule | gotcha | clarify | refuse |
|---|---|---|---|---|---|---|---|
| GLM 5.3 Flash, schema only (S0) | 93.1% | 90.7% | 27.9% | 12.8% | 75.7% | 84.0% | 100.0% |
| GLM 5.3 Flash + dictionary, baseline (S1) | 91.4% | 81.4% | 97.7% | 92.6% | 88.3% | 84.0% | 100.0% |
| Nemotron 3 Ultra + dictionary (S2) | 84.5% | 72.1% | 86.0% | 85.2% | 81.6% | 96.0% | 100.0% |
| GLM 5.3 Flash + harness (S4) | 96.6% | 88.4% | 95.3% | 96.6% | 94.2% | 84.0% | 100.0% |
| GLM 5.3 Flash fine-tuned (S5) | 96.6% | 95.3% | 97.7% | 96.6% | 97.1% | 100.0% | 100.0% |
| GLM 5.3 Flash fine-tuned + harness (S5H) | 66.7% | 100.0% | 66.7% | 69.2% | 75.0% | - | - |
| GLM 5.3 Flash + harness → Nemotron 3 Ultra (S6) | 98.3% | 83.7% | 97.7% | 96.6% | 91.3% | 80.0% | 100.0% |
