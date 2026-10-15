# C02 Deterioration Detector — semantics `c02-v2`

`c02-v1` runs stay stored exactly as computed (never recomputed). v1 known limits: no source check between windows; paired
denominator only checked by sum ≥ minimum; no correction-chain proof stored.

All computation happens in `public.run_deterioration_analysis(tenant, subject, expected_profile, as_of?)`.
Inputs from the browser are ids only. `as_of` (end of the event windows, on `observed_at`) defaults to today 00:00 UTC and may not be
in the future. `data_cutoff` = `now()` of the run: only observations with `ingested_at ≤ data_cutoff` are used, including when
resolving correction chains. Input hash = algorithm + approved (immutable) profile id + subject + as_of + (id, payload_hash) of every
observation ingested up to the cut-off. Same hash → the original run is reused with its original cut-off; late data or a
correction → new run with `revision_of` the previous run for the same profile + as_of.

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
  A paired denominator needs its OWN `expected_cadence_days` and `min_coverage_pct` (else `insufficient_config`), windows must be
  multiples of its cadence, its own coverage must be met, its fingerprint-compatible observations only (others →
  `denominator_incompatible_observations`), and its single source must equal the numerator's source in that window.
- Each window stores `source`, `denominator_source`, denominator coverage and `corrections` (used id → superseded ids).
- More than one source in a window → insufficient (no merge rule). No observations → insufficient (never zero).
- Different sources between baseline / reference / current windows (numerator or denominator) → `source_mismatch_across_windows`
  (no equivalence rule exists yet).

## Rule
- metric = value (absolute) or (value − baseline) / |baseline| · 100 (relative; baseline 0 → insufficient).
- Operator must agree with direction (higher_is_better → `<`/`≤`; lower_is_better → `>`/`≥`); relative threshold must be a worsening.
- `deterioration_candidate` ⇔ every current window meets the rule AND the reference window does not (temporal change required).
- All current + reference meet → `persistent_condition` (not a new deterioration; does not prove there was no earlier deterioration).
  Otherwise `no_deterioration` = criterion not met in the analysed windows only.
- Known MVP limit: a progressive decline that stays above the threshold, or crossed it before the reference window, is not flagged.
- `below_target` (gap) is reported separately from the temporal status.
- Context → `not_evaluated`; text → `unsupported`. Usage candidates never count as outcome candidates; `actionable_case` is always false.
