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

## V5 native uncertainty-analysis addition

`rules/36-uncertainty-error-analysis.md` is a V5-native quality owner added after auditing NIST
uncertainty guidance, NASA model-and-simulation credibility requirements, and European Commission
JRC uncertainty/sensitivity guidance. It does not replace or alter the exact V1, V3, or V4 owners.
The controller routes it beside those preserved layers for specification, verification, robustness,
and manuscript work. Its regressions protect source classification, evidence-based ranges,
`tested` versus `quantified`, implementation-error rollback, and prohibition of invented
probability distributions.

## V6 P0 governance repair

The project owner explicitly approved four bounded repairs on 2026-08-02: proportional R0/R1/R2
recovery, component-authoritative project state, discriminated start/end receipt validation, and an
explicit authorization boundary for Skill mutation. V6 changes the controller and its mechanical
validators only; it does not alter the exact V1 detailed rules or V3/V4 acceptance files.

Behavioral regressions cover same-session R0 continuation, component-summary mismatch, valid end
receipts, and rejection of unsafe legacy recovery behavior. P1 proposals for section-level routing,
approval consolidation, and Markdown mathematics remain deliberately unimplemented.

## V6 manuscript four-part-chain repair

On 2026-08-02 the project owner identified a repeated evaluator-visible failure: manuscript sections
and abstracts did not make the sequence “model, algorithm, result, error/sensitivity analysis”
explicit, while independent cross-solving was incorrectly promoted as manuscript validation.
`rules/36-uncertainty-error-analysis.md` now owns the four-part abstract and body gates and keeps
independent implementations in internal verification unless they produce a relevant error bound or
sensitivity conclusion. `scripts/test_uncertainty_contract.py` and `scripts/validate_skill.py`
mechanically reject removal of these guards. This is a V6-native strengthening; it does not replace
or alter the exact V1, V3, or V4 integrations.

## V6 shared-foundation, algorithm-replay, and propagation repair

On 2026-08-02 the project owner approved a bounded Skill repair after a multi-question physical
manuscript exposed three repeatable failures: a shared model chapter could swallow each question's
local model/algorithm chain; solver names could stand in for a replayable algorithm explanation;
and a body restructure could leave the abstract, analysis, symbols, evaluation, and conclusion on
the old organization. The first patch put both the consumer-propagation gate in `03` and the generic
algorithm-replay gate in `36`. A subsequent R2 full audit found that this duplicated
`rules/15-pipeline-methodology.md`'s declared propagation ownership and exceeded `36`'s
uncertainty/error-only responsibility. The corrected repair keeps the shared-foundation
non-substitution and reader-facing algorithm-replay gates in the V1-preserving manuscript superset
`rules/03-paper-content-rules.md`; propagation remains owned by `15`, and `36` retains only the
four-part chain's error/sensitivity identity and boundary. Regression guards check those owners
directly. Exact V2--V4 owners remain byte-for-byte unchanged. No contest-specific model, parameter,
result, or fixed heading template is migrated.

## 2026-08-03 manuscript reader, derivation, and source-ownership repair

User-authorized Skill maintenance generalized three failures observed in a live manuscript revision.
The active manuscript construction superset now prohibits evaluator-visible audience/audit meta-language,
requires a source-by-source physical bridge before compact equations, and assigns each LaTeX body file
to exactly one first-level heading. The controller also requires a complete read of every manuscript
rule before the first manuscript mutation in each new or recovered window. `17` adds the corresponding
audit failure and regression checks. These additions preserve all V1 lines and the substantive V2 reader
gate; they do not change any V3/V4 exact acceptance owner, contest-specific model, result, or layout rule.

## 2026-08-03 manuscript-round and propagation gate repair

A repeated manuscript failure showed that the first-window read gate could be reused for later user
edit instructions and that schema-valid receipts could not reject cross-section propagation without
a placement plan. The active controller now treats each new user-authorized manuscript edit as a
new mutation round, requires fresh complete routed-rule evidence, and requires a propagation matrix
plus rollback baseline before edits spanning two or more first-level sections. The manuscript,
reader-audit, receipt, and execution-gate owners are strict supersets of their preserved sources;
regressions reject missing current-round evidence and missing propagation artifacts. This repair
adds no contest-specific method, result, wording template, or layout rule.

## 2026-08-03 optimization-model and algorithm-visibility repair

Teammate review of an S7 optimization manuscript exposed two repeatable reader failures: a mathematically
complete optimization model could scatter its decision variables, objective, constraints, and output
across several paragraphs; and a solve section could begin with formulas before giving the whole-question
route. The V1-preserving manuscript superset `rules/03-paper-content-rules.md` now requires these four
optimization components to be visible in one continuous local block and requires a formula-free solve
overview before implementation details. The implementation layer pairs each action with a formula or
auditable criterion and its stage output, without forcing artificial formulas for ranking, boundary, or
stopping actions. Behavioral and structural regressions protect both guards. The exact V3 acceptance
owner `rules/25-model-results-acceptance.md` remains byte-for-byte unchanged; no contest-specific model,
numeric result, fixed heading recipe, or one-sentence/one-formula quota is introduced.

The same review then clarified the required presentation granularity. The active manuscript owner
now keeps each optimization label adjacent to its description and formula, requires visibly numbered
algorithm steps with a named mathematical method and implementation relation, and the uncertainty
owner requires a named analysis tool plus its governing numerical relation. Independent same-value
recomputation is explicitly excluded from evaluator-visible error/sensitivity prose, captions, and
tables unless it produces genuinely new error, convergence, propagation, or decision information.

## 2026-08-03 natural optimization-narrative correction

Review of officially displayed same-topic CUMCM papers showed that the preceding repair overfit a
review checklist: mandatory labels, a formula-free preamble, visible numbering, and action-to-formula
pairing could make otherwise sound mathematical prose read like an operating manual. The active
manuscript owner now protects semantic completeness rather than a fixed surface template. Optimization
models still expose decisions, feasibility, objective, and output locally, but may follow their natural
mathematical dependency; labels are optional navigation and repeated four-item summaries are rejected.
Solve sections still expose the algorithmic route, updates, criteria, stopping scope, and answer recovery,
but numbering is used only when it aids replay and formulas appear only where they carry mathematical
information. The uncertainty owner likewise keeps real method--relation--impact evidence while removing
the fixed four-sentence abstract quota. Exact V2--V4 acceptance owners remain byte-for-byte unchanged.

## 2026-08-18 provisional-artifact disposition repair

A live S1 interpretation turn exposed a repeatable workflow failure: the controller correctly
forbade promotion before human approval, but a complete task card was delivered only in chat instead
of being saved as a clearly provisional planning artifact. The existing prose already routed pending
analysis to `planning/analysis/`; the missing layer was mechanical receipt enforcement. Start receipts
now declare `substantive_analysis` and an `artifact_plan`, while end receipts report the realized
artifact and authority status. The validator rejects substantive analysis with only a chat/no-artifact
disposition and rejects complete turns with unrealized planned artifacts. Behavioral regressions cover
both failures. This repair adds no contest-specific task, model, parameter, result, or manuscript rule.
