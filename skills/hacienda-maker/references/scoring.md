# Scoring Formulas

## Trigger Score

For each query q in trigger-eval.json:

```
pass_rate_q = count(run_i where triggered_i == should_trigger) / runs_per_eval
```

A query passes if `pass_rate_q >= 0.5`.

```
trigger_score = (count of passing queries / total queries) * 100
```

## Functional Score

For each eval e across N runs:

```
median_pass_rate_e = median(pass_rate_run_1, pass_rate_run_2, ..., pass_rate_run_N)
```

An eval passes if `median_pass_rate_e >= 0.5`.

```
functional_score = average(median_pass_rate_e for all evals) * 100
```

## Combined Score

```
combined_score = trigger_score * weights.trigger + functional_score * weights.functional
```

Default weights: trigger=0.4, functional=0.6.

## Delta and Improvement

```
delta = combined_score - previous_best
is_improvement = delta > noise_floor   # strictly greater than, never >=
```

Default noise_floor: 2.0. A delta exactly equal to noise_floor is NOT an improvement.

## passed_evals / failed_evals Counters

These counters in `functional_detail` use threshold 0.5:
- `passed_evals`: evals with `median_pass_rate >= 0.5`
- `failed_evals`: evals with `median_pass_rate < 0.5`
