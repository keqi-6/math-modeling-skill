# V1–V3 to V4 migration ledger

This file preserves provenance. It is not an active permission source.

## Architecture decision

V4 does not select one prior version as its base:

- V1 supplies detailed project knowledge, failure cases, and long-form checks.
- V2 supplies concise evaluator-visible quality rules.
- V3 supplies recovery, receipts, stable identities, and regression-test intent.
- V4 replaces all distributed governance with one controller.

No prior version is modified or deleted.

## Responsibility mapping

| Responsibility | V1 principal source | V2/V3 principal source | V4 unique owner | Treatment |
|---|---|---|---|---|
| project recovery and full reading | `SKILL.md`, `01`, `14` | V2 main; V3 K-01/K-02, L-01 | `SKILL.md` §§1,4 | merged and centralized |
| state order and no jumping | V1 stages 0–9; `15` | V3 K-03/K-05, L-03 | `SKILL.md` §§2–3 | replaced by one state machine |
| authorization boundary | V1 human governance | V2 main/H; V3 K-04/H-01 | `SKILL.md` §§3,5 | replaced by one permission formula |
| model necessity and selection | V1 stages 4–5, `15` | V2/V3 S-02/S-06, V3 L-03 | `SKILL.md` §5 + `rules/modeling.md` | permission centralized; quality retained |
| external guidance and examples | V1 source/provenance modules | V2/V3 E-03 and source portfolios | `SKILL.md` §5 external boundary | rewritten from observed failure |
| raw-data audit | V1 `16` and stage 3 | V2/V3 A-03, E-02 | `rules/data.md` | condensed |
| modeling and solution | V1 `03`, `07`, stages 4–7 | V2/V3 `23` | `rules/modeling.md` | condensed |
| verification and robustness | V1 `05`, `09` | V2/V3 S-09, E | `rules/verification.md` | separated from modeling |
| manuscript content | V1 `03`, `05`, `06`, `13`, `17` | V2/V3 `10`, `20`–`24` | `rules/manuscript.md` | condensed by function |
| figures, LaTeX, PDF | V1 `02`, `04`, `05`, `11` | V2/V3 `30` | `rules/visuals-layout.md` | condensed |
| evidence and provenance | V1 `01`, `05`, `10`, `12`, `15` | V2/V3 `40` | `rules/provenance-delivery.md` | condensed |
| handoff, drafts, promotion | V1 `10`, `11`, `14` | V2/V3 `50` | controller §9 + provenance rule | permission/quality separated |
| execution receipts | implicit across V1 | V3 `01` | controller §7 | simplified and made state-aware |
| rollback and propagation | V1 `05`, `12`, `15` | V2/V3 G-06/E-04/L-07/H-04 | controller §6 | centralized |
| rule routing | V1 router | V2 main; V3 routing matrix | controller §8 | simplified |
| algorithm reference | V1 `07` | source portfolios | historical V1 source | reference on demand, not active rule |
| detailed literature procedure | V1 `08` | source portfolios | historical V1 source | reference on demand |

## Deliberate removals from active rules

The following remain available in V1–V3 but are not duplicated as active V4 obligations:

- tool-specific command examples;
- fixed directory trees when the existing project has a different valid structure;
- generic algorithm catalogues unrelated to the active problem;
- repeated versions of human-control language;
- repeated abstract/manuscript audits with equivalent functions;
- historical citations used to justify rule development;
- exact legacy rule numbering.

These are compression or authority changes, not deletion of the underlying quality responsibility.

## Known-risk coverage

| Failure | V4 control |
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

