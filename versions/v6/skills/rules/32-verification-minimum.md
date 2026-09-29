# Verification and robustness quality

Apply this file after an implementation or claim exists and the controller permits `S6_VERIFY`.

## Independent verification

- Recompute critical inputs, constraints, objectives, rankings, and headline values independently
  of the primary summary.
- Verify manifests, hashes, dimensions, units, tolerances, and producer identities.
- Test a small case by hand or exhaustive enumeration when feasible.
- Treat agreement with another implementation as corroboration, not proof of global optimality.

## Risk-matched testing

Choose tests for the actual failure mode:

- parameter sensitivity for policy or calibration dependence;
- deletion, resampling, or perturbation for sampling fragility;
- alternative baselines for method dependence;
- constraint relaxation or tightening for feasibility dependence;
- holdout or blocked validation for prediction;
- rank, confounding, or identifiability diagnostics for effect claims;
- boundary and adversarial cases for algorithms.

For every test state the object, operation, criterion, result, and proof boundary. A failed test
must reopen the earliest affected state; do not conceal it by weakening prose.

## Claim strength

Keep numerical correctness, model adequacy, stability, statistical uncertainty, causal meaning,
optimality, and real-world feasibility separate. State what each check proves and does not prove.

