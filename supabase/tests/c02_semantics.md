# C02 Deterioration Detector — semantics `c02-v1`

All computation happens in `public.run_deterioration_analysis(tenant, subject, expected_profile, as_of?)`.
Inputs from the browser are ids only. `as_of` defaults to today 00:00 UTC and may not be in the future.

## Windows (UTC, closed-open `[start, end)`)
- W = `observation_window_days`, N = `deterioration_consecutive_windows`, C = `comparison_window_days`.
- current_k = `[as_of − k·W, as_of − (k−1)·W)`, k = 1..N; reference = `[as_of − (N+1)·W, as_of − N·W)`.
- trailing baseline = `[as_of − N·W − C, as_of − N·W)`; fixed baseline = `baseline_value`. `reference_period` → unsupported.

## Per window
- Effective observations: corrections resolved to the leaf of the chain; forks → `ambiguous_correction`; other
  profile versions only if the indicator fingerprint (unit, value type, classification, direction, definition) is equal.
- Aggregation: `mean` | `sum` | `last` (tie at the last instant → insufficient). `sum` with trailing baseline requires C = W.
- Coverage = distinct cadence slots (`expected_cadence_days`) with ≥1 observation / W÷cadence; must be ≥ `min_coverage_pct`.
- Denominator: `observation_count` (n) or `paired_indicator` (sum of another numeric indicator, same window); must be ≥ `min_denominator`.
- More than one source in a window → insufficient (no merge rule). No observations → insufficient (never zero).

## Rule
- metric = value (absolute) or (value − baseline) / |baseline| · 100 (relative; baseline 0 → insufficient).
- Operator must agree with direction (higher_is_better → `<`/`≤`; lower_is_better → `>`/`≥`); relative threshold must be a worsening.
- `deterioration_candidate` ⇔ every current window meets the rule AND the reference window does not (temporal change required).
- All current + reference meet → `persistent_condition` (not a new deterioration). Otherwise `no_deterioration`.
- `below_target` (gap) is reported separately from the temporal status.
- Context → `not_evaluated`; text → `unsupported`. Usage candidates never count as outcome candidates; `actionable_case` is always false.
