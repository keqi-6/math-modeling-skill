# V1–V4 to V5 migration ledger

This file preserves provenance. It is not an active permission source.

## V5 repair criterion

A failure is marked covered only when four layers agree: an active rule states the prohibition, a
structured receipt or manifest represents the required evidence, a validator rejects missing or
inconsistent evidence, and a negative regression reproduces the unsafe path. Text-only coverage is
not sufficient.

## V4 regression found during full-version audit

V4 centralized the state machine correctly but lost V3 G-02's mechanically checkable reading proof.
Its receipt validator checked only `earliest_open_state` and decision permission. It accepted any
`full_read_gate` value and did not inspect inventories, hashes, read ranges, truncation, unresolved
files, or S0 mutation. Its five regressions tested model approval only. Therefore V4's ledger claim
that stale handoff and edit-before-recovery were “covered” was stronger than its executable evidence.

V5 retains the V4 controller and restores the lost V3 evidence contract through:

| Failure path | Active rule | Structured evidence | Validator | Negative regression |
|---|---|---|---|---|
| custom prose used as gate closure | `SKILL.md` §4 | gate enum | `validate_receipt.py` | `custom_gate_value` |
| closed without current evidence | §4 recovery contract | `recovery_evidence` | receipt validator | `closed_without_evidence` |
| incomplete/truncated reading | §4 recovery contract | ranges and `truncated` | manifest verifier | `truncated_output` |
| stale file inventory | §4 recovery contract | path/size/hash snapshot | manifest verifier | `stale_inventory` |
| unresolved material hidden | §4 recovery contract | `unresolved` | manifest verifier | `unresolved_item` |
| invented completion counts | §7 receipt | verified counts | receipt validator | `count_mismatch` |
| project mutation during S0 | §4 and permission table | state/gate/action fields | receipt validator | `s0_mutation` |
| summary or prior audit substitutes for reread | §§1,4 | current manifest identity | live inventory verification | stale/closed-without-evidence cases |

The verifier can prove current inventory identity and completeness of recorded inspection evidence;
it cannot prove private cognition. V5 states this limit instead of converting a script pass into a
claim that reading actually occurred.

## Architecture decision

V5 does not select one prior version as its base:

- V1 supplies detailed project knowledge, failure cases, and long-form checks.
- V2 supplies the reader-first evaluator-visible audit and its manuscript/audit triggers.
- V3 supplies recovery, receipts, stable identities, and regression-test intent.
- V4 supplies the unified controller and exposes the recovery-validation regression.
- V5 places every V1 authority directly in its own active `rules/` or `scripts/` path and adds the
  controller and mechanical guards from V3–V5.

No prior version is modified or deleted.

## Exact acceptance-layer repair

The first V5 draft mapped nine V3 stable-ID quality files and six V4 quality files to fuller V1
owners by semantic assertion. That preserved useful detail but did not mechanically prove that every
concise acceptance condition survived. V5 now integrates those fifteen historical files byte for
byte as active acceptance and cross-check modules under `rules/21`–`rules/35`.

The controller remains the only permission authority. Rules `01`–`17` provide detailed procedures;
rules `21`–`29` impose V3 stable-ID acceptance criteria; rules `30`–`35` impose V4 concise
cross-checks. An overlap is cumulative, not competing: execute the detailed procedure and satisfy
the exact acceptance criterion. `validate_version_deltas.py` rejects a missing file, changed hash,
changed owner, semantic-only downgrade, or absent route, and `test_version_deltas.py` reproduces each
of those failure classes.

The authoritative completeness proof is `v1-integration-map.json` plus
`scripts/validate_v1_migration.py`. The map covers all 17 V1 Markdown authorities and both reusable
V1 Python tools by exact active-file hash. Exact integration is the safe baseline; future semantic
compression may replace an integrated source only after an atomic mapping and failure regression prove no
independent obligation disappeared.

`version-delta-map.json` separately adjudicates every material V2–V4 delta examined: adopted
additions, detailed-rule replacements, strengthened validators, and rejected stale relocations.
Each entry carries the historical hash, active owner, treatment, route, and reason. Validate these
against the version directories with `scripts/validate_version_deltas.py --history-root .`; V1
coverage alone is not a V1–V5 completeness claim.

## Responsibility mapping

| Responsibility | V1 principal source | V2/V3 principal source | V5 owner | Treatment |
|---|---|---|---|---|
| project recovery and full reading | `SKILL.md`, `01`, `14` | V2 main; V3 K-01/K-02, L-01 | `SKILL.md` §§1,4 | merged and centralized |
| state order and no jumping | V1 stages 0–9; `15` | V3 K-03/K-05, L-03 | `SKILL.md` §§2–3 | replaced by one state machine |
| authorization boundary | V1 human governance | V2 main/H; V3 K-04/H-01 | `SKILL.md` §§3,5 | replaced by one permission formula |
| model necessity and selection | V1 stages 4–5, `15` | V2/V3 S-02/S-06, V3 L-03 | `SKILL.md` §5 + `rules/07`, `rules/15` | permission centralized; V1 detail integrated |
| external guidance and examples | V1 source/provenance modules | V2/V3 E-03 and source portfolios | `SKILL.md` §5 external boundary | rewritten from observed failure |
| raw-data audit | V1 `16` and stage 3 | V2/V3 A-03, E-02 | `rules/16-data-audit-methodology.md` | exact active integration |
| modeling and solution | V1 `03`, `07`, stages 4–7 | V2/V3 `23` | `rules/03`, `rules/07`, `rules/15` | exact active integration |
| verification and robustness | V1 `05`, `09` | V2/V3 S-09, E | `rules/05`, `rules/09` | exact active integration |
| manuscript content | V1 `03`, `05`, `06`, `13` | V2/V3 `10`, `20`–`24` | `rules/03`, `rules/05`, `rules/06`, `rules/13` | exact active integration |
| figures, LaTeX, PDF | V1 `02`, `04`, `05`, `11` | V2/V3 `30` | `rules/02`, `rules/04`, `rules/05`, `rules/11` | exact active integration |
| evidence and provenance | V1 `01`, `05`, `10`, `12`, `15` | V2/V3 `40` | corresponding numbered `rules/` modules | exact active integration |
| handoff, drafts, promotion | V1 `10`, `11`, `14` | V2/V3 `50` | controller §9 + `rules/10`, `rules/11`, `rules/14` | permission/quality separated |
| execution receipts | implicit across V1 | V3 `01` | controller §7 | simplified and made state-aware |
| rollback and propagation | V1 `05`, `12`, `15` | V2/V3 G-06/E-04/L-07/H-04 | controller §6 | centralized |
| rule routing | V1 router | V2 main; V3 routing matrix | controller §8 | simplified |
| algorithm reference | V1 `07` | source portfolios | `rules/07-algorithm-reference.md` | exact active integration |
| detailed literature procedure | V1 `08` | source portfolios | `rules/08-literature-search.md` | exact active integration |

## Preserved detail versus everyday loading

Earlier V4 drafts described the following as deliberate removals from active rules:

- tool-specific command examples;
- fixed directory trees when the existing project has a different valid structure;
- generic algorithm catalogues unrelated to the active problem;
- repeated versions of human-control language;
- repeated abstract/manuscript audits with equivalent functions;
- historical citations used to justify rule development;
- exact legacy rule numbering.

That wording could not prove rule preservation and is retired. V5 directly integrates the complete
V1 sources, including examples, fixed-tree guidance, catalogues, repeated formulations, citations,
and numbering. It also preserves the V3 and V4 quality layers exactly rather than asking a validator
to infer semantic equivalence from a reason field.
Progressive routing controls when a file is loaded; it does not delete the text or silently downgrade
its independent obligations. Controller permissions and current official/user requirements still
take precedence where an integrated historical example or default conflicts.

## Known-risk coverage

| Failure | V5 control |
|---|---|
| accept stale handoff as truth | `S0_RECOVER` and full-read gate |
| edit before project recovery | S0 permission table |
| add a model because a rubric mentions it | decision gate and external-guidance boundary |
| interpret “continue” as model approval | explicit non-approval list |
| implement a verified candidate automatically | decision package and permission formula |
| fix a model defect only in prose | rollback mapping |
| claim whole-project completion from local checks | receipt completion scope |
| compile without page inspection | visuals/layout PDF checks |
| promote a draft without human review | S7 completion and provenance rule |

## Future migration rule

When a legacy detail appears missing:

1. identify the concrete failure that the detail prevents;
2. determine whether it controls permission or defines quality;
3. place permission only in `SKILL.md`;
4. place quality in exactly one file under `rules/`;
5. add or extend a behavioral regression test;
6. avoid restoring the full legacy paragraph unless its independent meaning requires it.
