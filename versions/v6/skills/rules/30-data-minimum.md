# Data quality

Apply this file only after the controller permits `S2_ASSESS` data work.

## Data identity

- Preserve original files immutably and record hashes.
- Identify the observational unit, experimental unit, repeated measure, cluster, time or spatial
  level before analysis.
- Distinguish missing values, structural absence, censored values, zeros, outliers, and parse errors.
- Record units, percentage conventions, encodings, sheet meanings, keys, duplicates, and ranges.
- Never treat repeated measurements from one experiment as independent experiments.

## Transformation and cleaning

- Make every cleaning, recoding, merge, exclusion, imputation, and derived field explicit.
- Reconcile raw and cleaned row counts, columns, keys, aggregates, and representative records.
- Preserve a mapping back to the original row or cell.
- Do not delete an outlier merely because it harms a preferred model.
- Explain how each material treatment changes the claims the data can support.

## Evidence capacity

- Compare the requested effects with the actual design: replication, balance, overlap, confounding,
  rank, support, and extrapolation.
- Separate association, controlled local comparison, prediction, causal effect, and mechanism.
- State identifiable and non-identifiable quantities.
- Build the simplest hand-checkable baseline before proposing a more demanding method.

## Outputs and checks

Freeze cleaned data, data dictionary, audit summary, anomaly ledger, transformations, hashes, and
independent reconciliation. Visual audit figures must answer a named data-quality question.

