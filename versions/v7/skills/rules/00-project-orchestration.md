# 00 — 详细项目编排参考

本文件保留完整的项目实施程序，但不是独立 Skill、第二入口或第二状态机。唯一入口、权限、
批准、回退和完成状态由同目录 `SKILL.md` 决定；本文件只能在控制器已经允许相应动作后，
说明如何执行。下文历史形成的 Stage 0–9 是工作类别和检查清单，不是可单独晋升的状态。

| 本文件工作类别 | V7 控制器状态 |
|---|---|
| Stage 0 ORIENT、Stage 1 SOURCE | `S0_RECOVER`、`S1_INTERPRET`、`S2_ASSESS` 中的对应工作 |
| Stage 2 UNDERSTAND | `S1_INTERPRET` |
| Stage 3 DATA | `S2_ASSESS` |
| Stage 4 EVIDENCE AND DESIGN | `S2_ASSESS` → `S3_DECIDE` → `S4_SPECIFY`，不得合并批准 |
| Stage 5 SOLVE PER SUBPROBLEM | `S4_SPECIFY` → `S5_IMPLEMENT` → `S6_VERIFY` |
| Stage 6 INTEGRATE、Stage 7 STRESS | `S6_VERIFY` |
| Stage 8 COMMUNICATE | `S6_VERIFY` 形成逐问队友讲解稿及声明—证据—论文落点映射；论文正文统一属于 `S7_PUBLISH` |
| Stage 9 AUDIT AND SUBMIT | `S6_VERIFY` → `S7_PUBLISH`，正式晋升须人工批准 |

## Skill architecture and routing

This directory is one skill package with routed supporting modules. During ordinary work, numbering
identifies files and module loading follows the current task. This progressive loading rule never
reduces the mandatory full-project rereads at session activation, recovery, milestone closure, or
finalization.

| Layer | Authority | Responsibility |
|---|---|---|
| Orchestration | `SKILL.md` | State selection, permission, approval, rollback, completion, and routing |
| Orchestration procedure | `00-project-orchestration.md`, `15-pipeline-methodology.md`, `14-session-handoff.md` | Dependency detail, project work categories, recovery procedure, and handoff evidence within controller permission |
| Construction | `01`, `02`, `03`, `04`, `07`, `08`, `09`, `10`, `16` | Define how to build one kind of artifact |
| Evaluation | `05-audit-protocol.md`, `11-paper-finalizer.md` | Check existing artifacts and decide readiness |
| Source-derived rule portfolios | `06-weiwei-norms.md`, `13-excellent-paper-expression.md` | Preserve and classify rules learned from lectures, public papers, and writing guidance; source type does not lower rule force |
| Provenance and governance | `12-source-audit-and-provenance.md` | Verify sources, rule hierarchy, feedback migration, and deletion approval |

Resolve overlap by ownership:

- `03` owns the canonical paper-content specification. `06` and `13` are classified rule
  portfolios: their A/B/C rules must be applied through the relevant construction or evaluation
  owner, while D items remain diagnostics and E items await human disposition.
- `04` owns figure/table design; `05` only checks whether the result passes.
- `08` owns literature discovery, `12` provenance and rule hierarchy, and `03` manuscript citation use.
- `09` owns robustness-test design; `05` audits the evidence for robustness claims.
- `10` owns machine artifact lineage; `14` owns human/session recovery state.
- `16` owns raw-data audit, structured preprocessing and audit-stage visualization methodology;
  `04` owns publication figure design after the data and claim semantics are fixed.
- `11` owns submission assembly and boundaries, not paper drafting or the full audit protocol.

### Rule force and deletion governance

Classify each rule independently of its source:

| Label | Meaning | Execution |
|---|---|---|
| A | Hard rule supported by official requirements, mathematical correctness, truthfulness, or approved governance | Must execute when in scope |
| B | General quality rule with a checkable defect and outcome | Execute unless a documented task-specific exception applies |
| C | Conditional rule | Execute only after its stated template, format, task, or evidence condition is verified |
| D | Heuristic, preference, or diagnostic technique | Consider and use when helpful; never fail an artifact solely for omitting it |
| E | Mechanically unsafe, overbroad, conflicting, or source-unverified item | Preserve for review but do not enforce as a pass/fail rule |

Never infer force from phrases such as “lecture-derived”, “excellent-paper pattern”, “increment”, or
“recommendation”. Conversely, a useful source does not turn all statements in its file into hard
rules.

When a rule has a clear defect and a clear replacement that preserves its useful purpose, rewrite it
and propagate the correction without requiring item-by-item approval. Ask the user only before a
pure deletion with no replacement, or before merging/moving rules when an independent meaning or
competing version would disappear. For such deletions, present the stable ID, current wording,
classification, reason, retained coverage, and consequence. Unapproved deletion candidates remain
visible in a pending-decision register.

For a teacher, reviewer, or user feedback-only stage, read `12` first, then the single construction
authority implicated by the feedback, and finally the corresponding checklist portion of `05`.
Do not load unrelated modules or modify project artifacts without separate authorization.

### Two mandatory full-read gates

At a newly activated session, inherited workspace, context-loss recovery, milestone closure, or
final-paper closure, inventory and inspect the entire project before making a project-state or
synchronization claim. `HANDOFF.md`, `project_state.json`, README files, logs, and chat summaries
are navigation aids only; none may substitute for this reread.

“Entire project” includes original statements and attachments, rules and templates, communications,
planning and audits, references, data, source code, configurations, frozen outputs, documentation,
paper source, figures, compiled PDF, appendices, scripts, current skill files, delivery mirrors,
archives, and unknown files. Apply the representation appropriate to each file:

- read every unique text/code/configuration source completely;
- extract and inspect every sheet, page, diagram, table, and embedded object in office files;
- visually inspect images and every page of evaluator-visible PDFs;
- inspect structured/binary data by schema, dimensions, ranges, invariants, producer, and key values;
- hash identical mirrors or duplicates, read one canonical copy completely, and prove equality;
- inventory caches, lock files, and build intermediates and verify their role, without treating them
  as independent project evidence.

At startup/recovery, build the current state from this evidence and only then compare it with the
handoff summaries. At closure, repeat the inventory after all changes, trace each local change through
every dependent artifact, check for stale references and mirrors, and establish synchronization by
content comparison rather than by the fact that a copy command ran. A local edit is not closed until
the full-project impact audit shows that every affected representation is updated or explicitly
recorded as intentionally unchanged.

## Start condition

Use this workflow when the project root contains original problem material and this `skills/`
directory, even if no README, source code, planning documents, outputs, or paper exists.

Treat original problem files as immutable evidence. Do not infer the task from filenames alone.
Read the actual statement and attachments before proposing a model.

## Human-led governance

Treat the user as the project owner and decision maker. AI may reduce workload by reading sources,
auditing data, deriving candidate formulations, implementing approved mathematics, running
experiments, checking consistency, preparing alternative prose, and performing mechanical
validation. It must not convert its own proposal into an accepted project decision.

Before an artifact becomes a project authority or evaluator-visible output, conduct a deep
interaction that makes clear:

- what question the artifact answers and what evidence it uses;
- which interpretations, assumptions, metrics, model family, parameters, baselines and claim scope
  it adopts;
- what credible alternatives exist and what accepting the choice excludes;
- what the AI contributed, what remains uncertain, and what the user is being asked to decide.

Record the user's decision and only then implement or promote the artifact. Drafts created to support
the discussion must be marked provisional and kept out of authoritative planning, frozen outputs,
paper text and delivery mirrors until accepted. Silence, lack of objection, an existing codebase, or
a previous AI-generated draft does not count as approval.

After approval, AI may autonomously perform reversible mechanical work within the accepted
specification, such as coding, running, formatting, cross-checking and synchronizing. Return to the
user whenever evidence contradicts the accepted choice or a change would alter modeled reality,
evaluation criteria, mathematical specification, claimed conclusion or delivery scope.

Human approval must be informed rather than ceremonial. When the user or team reports weak
foundations in programming, mathematics, statistics, or the application domain, give each material
method and result a reader layer in this order:

`question → minimal worked example → project calculation → result → practical meaning → limitation`

Preserve the technical reproduction layer, but do not treat terminology, successful execution,
independent verification, or absence of objection as evidence that the user understood the method.
Before promoting a stage artifact, ask the user to review the small set of method meanings and
boundaries that they must be able to explain. Record unresolved comprehension as an open stage gate,
not as approval of the underlying decision.

Do not leave a material understanding review only in chat. Add a plain-language section to the
current question's analysis or method document, organized as:

`question → smallest numerical example → project data structure → method roles → identifiable and
non-identifiable claims → credible alternatives → what confirmation does and does not approve`.

Keep the technical layer beside it or link it directly. Close the understanding gate only after the
user explicitly confirms this reader layer. Record that confirmation separately from later model,
parameter, implementation, or manuscript approval.

Apply a terminology-minimization gate to chat, planning documents, reports, figures and manuscript
prose whenever the user or intended reader may lack the relevant background:

1. First ask whether the term changes a decision, defines a method that must be reproduced, or is
   required for accurate citation and retrieval. If none applies, replace it with ordinary language.
2. If the term is necessary, first state in ordinary language what object is handled, what action is
   performed and what the result means; then give the standard term once in parentheses if useful.
3. Do not introduce more new terms in one explanation than the reader needs for the immediate
   decision. Defer secondary names, historical labels, abbreviations and implementation vocabulary
   to a technical note.
4. A glossary, footnote or later section does not repair an unexplained term at its first use.
5. Before asking for approval, run a no-jargon restatement: the user-facing summary must remain
   sufficient to choose among the options after specialist names and abbreviations are removed.

Technical accuracy does not require maximum terminology density. Keep the standard name in the
reproduction or citation layer when it is genuinely needed, while making the decision layer
understandable without that name.

## Mandatory first actions

1. If `HANDOFF.md` exists, read it first only as a navigation hypothesis. Read
   `14-session-handoff.md`, then execute the full-read gate before accepting its stage, pause point,
   completion, page-count, validation, or synchronization claims.
2. Determine the contest, edition, deadline, deliverables, candidate problems, team capabilities,
   available software and current workspace state. Do not ask again for facts already provided.
3. Tell the user that the project bootstrap or recovery workflow is active and explain the current stage.
4. Inventory every file and folder, including `skills/`; classify statement, attachment, data,
   template, rule, reference, archive, mirror, cache, lock file, generated artifact, or unknown.
5. Execute the startup full-read gate. Do not replace it with spot checks, modification-time sorting,
   summaries, or a previous agent's file list.
6. Present the orientation findings and agree with the user on project purpose, applicable rules,
   candidate-problem status, collaboration boundaries and next artifact.
7. Run the non-overwriting bootstrap script only when the project has not already been initialized
   and the user has accepted this project structure:

   ```bash
   python3 skills/scripts/bootstrap_project.py --root .
   ```

8. Close the directory-realization gate immediately after bootstrap. A created directory is not a
   fulfilled responsibility:
   - resolve which inspected files are official statement, attachment, template, communication,
     temporary lock, mirror, archive, or unknown;
   - populate `data/` with non-destructive copies of confirmed official inputs when their size and
     layout make copying reasonable, while keeping the original source location and proving equality
     by hash/content comparison; use an explicit pointer manifest when copying would be large,
     ambiguous, collision-prone, or provenance-damaging;
   - never copy temporary locks, caches or unknown files into `data/` as official evidence;
   - verify that every other created directory either contains its declared initial authority or is
     explicitly marked as awaiting its producing stage. Do not report initialization complete from
     directory existence alone.
   Acceptance of the standard structure authorizes these reversible responsibility-realization
   steps for already confirmed official inputs; return to the user if official identity, copy scope,
   collision handling or provenance is uncertain.
9. Create or verify `planning/README.md` and `planning/project_plan.md`. Make the main body of the
   project plan the technical problem-solving dependency chain that the team will follow, normally:
   task interpretation → raw-data audit and structured preprocessing → exploratory analysis →
   simple baselines → candidate-model comparison with reasons → human model decision → mathematical
   specification → per-task solve and freeze → independent verification → robustness and
   applicability → cross-task integration → manuscript → reproducibility and final audit.
   Put schedule, governance and submission compliance in appendices or parallel sections unless the
   user explicitly asks for a management-first plan. Do not let stage labels substitute for concrete
   actions on the selected problem.
   For every original question and separately deliverable subquestion or scenario, instantiate a
   checkable substage list in the plan. At minimum distinguish task interpretation, approved data
   interface, triggered literature orientation, evidence re-review, simple baseline, candidate and
   sufficiency comparison, human method decision, mathematical specification, implementation,
   independent verification, robustness/explanation, and human review/freeze/paper mapping. Record
   the current substage, closing evidence and the action prohibited until it closes. A generic
   workflow paragraph or one status for the whole question does not satisfy this requirement.
   Functions may be combined when dependencies genuinely allow it, but their status and closing
   evidence must remain visible. Existing downstream code or verification never closes a skipped
   upstream decision or specification stage.
10. Fill or verify `planning/source_inventory.md`, `planning/understanding.md`, and
   `planning/task_matrix.md` from evidence.
11. Present the user with the candidate-problem decision or recovered state, task map, data facts,
   ambiguities, logical gaps, resource risks, and proposed next stage. Do not begin substantive model
   implementation before this first deep interaction.

If the workspace is already partially built, do not recreate it. Audit existing files against the
directory contract below and continue from the earliest incomplete phase.

## Project directory contract

| Path | Single responsibility |
|---|---|
| `data/` | Immutable official inputs or explicit pointers to original inputs; never store generated conclusions here |
| `references/` | External evidence, DOI/URL records, reading status, notes, and legally obtained local sources |
| `planning/` | Current planning authorities at its root, with pending analyses, dated audit snapshots, and superseded history separated below |
| `src/` | Executable source only; shared utilities separate from question-specific scripts |
| `output/` | Machine-generated frozen JSON/NPZ/CSV results; never hand-edit model conclusions |
| `docs/` | Per-question teammate solution briefs plus detailed method, derivation, verification, reproduction and defense explanations linked to real code and outputs; never manuscript drafts |
| `paper/` | The sole manuscript workspace and evaluator-visible delivery location; draft/formal status must be explicit and formal promotion requires S7 human approval |
| `skills/` | Cross-project workflow only; never write current problem node IDs, parameters, answers, or personal preferences here |
| `HANDOFF.md` | Project-specific cross-session state, pause point, evidence pointers, recent rollback and recovery instructions |

Keep official inputs in their existing location when moving them could alter provenance. Record
their paths and hashes in `planning/source_inventory.md`. After the user accepts the standard
structure, use non-destructive copies of confirmed official inputs in `data/` when reasonable and
prove equality; otherwise create explicit pointers. Moving originals, resolving ambiguous inputs,
or reorganizing provenance still requires a separate explanation and approval.

### Source-format syntax boundary

Match every text artifact to the syntax of its declared source format:

- In project `.md` files, use Markdown headings, lists, blockquotes, tables, links, inline code and
  fenced code blocks. Do not use LaTeX document commands, environments, citation commands or math
  delimiters such as `\section`, `\begin`, `\cite`, `\ref`, `\(...\)`, `\[...\]`, `$...$` or
  `$$...$$`. Express short mathematics in prose or Unicode; put longer formulas in a fenced
  `text` block and define their symbols immediately below. Use Markdown links for sources.
- In `.tex` files, use valid LaTeX for headings, emphasis, citations, cross-references, mathematics,
  figures and tables. Do not use Markdown headings, emphasis markers, link syntax, tables or fenced
  code blocks as document structure.
- Code fences inside this skill's own Markdown may contain LaTeX examples because they teach `.tex`
  construction; this exception does not authorize mixed syntax in project Markdown artifacts.
- Before closing a writing or synchronization task, scan the changed files for syntax belonging to
  the other format and inspect the rendered Markdown or compiled PDF as appropriate.

### Planning hygiene

Keep `planning/` navigable by authority rather than by file creation order:

- Apply the source-format syntax boundary to `README.md`, `HANDOFF.md`, `planning/**/*.md`,
  `docs/**/*.md` and every other project Markdown artifact. Reserve manuscript LaTeX for
  `paper/*.tex`.
- Keep only current cross-phase authorities and live logs at the root, such as
  `project_plan.md`, `source_inventory.md`, `understanding.md`, `terminology.md`, `inspiration.md`,
  `method_plan.md`, and `work_log.md`.
- Put unapproved conceptual studies, alternatives, and focused investigations in
  `planning/analysis/`; prefix them with `YYYY-MM-DD_` and declare whether they may enter the paper.
- Put version-specific checks in `planning/audits/` with `YYYY-MM-DD_<topic>.md`. Treat an audit as
  a snapshot, not as permanent proof that the current model or paper still passes.
- Put superseded plans, manifests, and audits in `planning/archive/`, grouped by date or version.
- Maintain `planning/README.md` as the authority map and add a local README in each nontrivial
  subdirectory. State which files are current, pending review, snapshots, or superseded.
- Keep one authority per responsibility. After an analysis is approved, merge its stable decisions
  into the relevant root authority; do not leave two competing “current” definitions.
- Update inbound links, handoff instructions, and mirrors after every move. Search for old paths
  before declaring the reorganization complete.

## Stage pipeline

Use the stages as a reasoning map, not as an autonomous workflow engine or a source of action
permission. Map every action back to the V7 controller state table above. The purpose is to remember
what a complete modeling project requires, recognize omissions, and know which earlier reasoning
must be revisited after a change. Do not impose scoring, automatic progression, fixed artifact
counts, or tool-driven decisions on the user.

Use `project_state.json` and planning records only as lightweight navigation when they help a long
project; the mathematical evidence remains authoritative. Read `15-pipeline-methodology.md` for
the full-work map, feedback logic, and paper mapping.

### Stage 0 — ORIENT

Goal: choose what project is actually being executed under real constraints.

- Confirm contest and edition, official rules, deadline, deliverables, language, anonymity, AI
  disclosure, team skills, compute/software availability, and expected collaboration mode.
- When several problems are available, compare them by data accessibility, domain burden,
  mathematical structure, verification feasibility, writing burden, and catastrophic failure risk.
- Record why one problem was selected and why alternatives were rejected. If the problem is already
  fixed, record that fact rather than simulating a selection exercise.
- Check early whether essential files, solvers, fonts, rendering tools and formats are usable; do
  not turn this into a mandatory automation layer when a direct inspection is sufficient.

Exit only when the project target, constraints, rule sources, and environment blockers are known.

### Stage 1 — SOURCE

Goal: know exactly what was provided.

- Extract the complete statement, attachment schemas, units, missing values, diagrams, and template
  constraints.
- Record file hashes and distinguish official files from temporary locks, mirrors, and archives.
- Produce `planning/source_inventory.md`.

Exit only when every original file has a disposition and unreadable material is explicitly listed.

Read `12-source-audit-and-provenance.md` for provenance and contamination rules.

When AI contribution, authorship, or disclosure is questioned, use that file before changing the
paper. Treat AI as a tool rather than an author or rights holder; document assistance, adoption,
human judgment, modification, verification, substantive human control, and final responsibility.
Apply explicit contest submission duties as written. Use Nature Portfolio policy only to interpret
undefined boundaries such as assisted copy editing, substantive generation, authorship, and
generative images; it has stronger conceptual guidance, not higher rule authority than the contest.

### Stage 2 — UNDERSTAND

Goal: turn the statement into a verified task map without choosing methods prematurely.

- Establish a canonical problem identity before naming tasks: distinguish contest/year, selected
  problem number or letter, and the statement's internal question/subquestion numbering. Treat the
  original statement as authoritative; use `planning/task_matrix.md` and the current paper headings
  as two derived cross-checks, not as independent sources that can create tasks.
- Before announcing a “next question,” creating a question-specific path, or adding a numbered
  heading, verify that the identifier appears in the original statement and agrees with the task
  matrix and paper structure. If the three disagree, stop progression, report the mismatch, and
  repair the derived artifacts from the statement. Never infer an internal “problem three” from a
  filename such as “third selected problem,” from stale `q3` code, or from a generic workflow.
- Complete a concept audit before selecting models. Define each core entity, institutional role,
  event type, region, boundary, and evaluative term; state what it is and what it is not.
- For every subproblem, extract subject, action, quantifier, scope, time state, scenario, and output.
  Do not expand a specified node, event, or period into all nodes, events, or periods.
- Separate the modeled object's duties from functions performed by the wider real-world system.
- Map each data field to conclusions it can support and conclusions it cannot support.
- Operationalize words such as reasonable, effective, safe, fair, feasible, robust, and optimal by
  naming the evaluated object, metric, baseline, threshold, and applicability conditions.
- Classify candidate requirements as explicit statement requirements, implicit executability,
  realism enhancements, applicability boundaries, or out-of-scope extensions.
- First inspect objects, quantifiers, time, space, resources, thresholds, and applicability. Use a
  minimal boundary counterexample when an interpretation contains strong quantifiers, extreme or
  threshold conditions, feasibility boundaries, extrapolation, or a claim stronger than the
  original task. State whether the counterexample refutes the original task, the current
  interpretation, or only the stronger claim introduced by the modeler. When no material boundary
  risk exists, check the statement, data range, and applicability directly instead of manufacturing
  a counterexample.
- Before adding a constraint to enforce a desirable property, check whether the current baseline
  rule already implies it; distinguish that baseline implication from a later model that relaxes
  the rule.
- Before asking the user to reconfirm a definition, assumption, metric, priority, or responsibility
  policy, audit whether an already approved decision can be inherited. Compare decision object,
  evaluation object, scenario, model role, and claim scope; inherit compatible choices, group
  material differences for review, and do not mechanically copy an entire objective order merely
  because metric names match.
- List every question, required output, known quantity, unknown quantity, constraint, evaluation
  criterion, and ambiguity.
- Separate facts stated by the problem from assumptions that a modeler may need to add.
- Search for logical incompleteness: missing initial time, speed, boundary condition, objective
  priority, ownership rule, or measurement definition.
- Build at least one hand-checkable data fact per task.

Deep-interaction gate: explain the task map and ambiguities to the user. The user decides any
interpretation or assumption that enters an authority or output. AI may recommend a conservative
choice, but may not silently promote it.

Store the concept audit in `planning/` first. If the user asks to review it before paper changes,
do not transfer the analysis into the paper until approval. Exit with an approved or explicitly
provisional concept audit, `planning/understanding.md`, and one task card per subproblem in
`planning/task_matrix.md`.

Read `01-contest-project-pattern.md` and the problem-analysis rules in
`03-paper-content-rules.md`.

### Stage 3 — DATA

Goal: establish what the attachments can support before choosing a model.

- Before writing the main audit script, freeze a project-specific data methodology in `planning/`.
  Define statistical units, raw-to-clean transformations, missing and structural-null semantics,
  diagnostic rules, expected tables/figures, validation checks, allowed claims and known failure
  modes. A script does not become the method authority merely because it ran successfully.
- Parse every table, sheet, diagram and relationship; record schema, units, keys, missingness,
  duplicates, ranges, impossible values, graph connectivity, time coverage and sampling granularity.
- Separate entity-, observation-, repeated-measure-, time- and scenario-level units before computing
  summaries. Do not create pseudo-replication by counting repeated attributes as independent entities
  or longitudinal observations as independent experimental replicates.
- Distinguish raw facts, corrected records, derived fields and analysis settings. Preserve raw data.
- Reconcile every retained raw field against the clean table, record structural nulls separately
  from missing values, and make parsing failures explicit. Statistical anomaly flags are diagnostics,
  not deletion instructions, unless external evidence and the user approve a treatment.
- Map fields to task-card variables and claims. Mark unavailable information rather than replacing
  it silently with a convenient proxy.
- Build hand-checkable samples and baseline summaries. For prediction or learning tasks, define
  leakage-safe train, validation and test logic before feature engineering.
- Give every audit figure a data level, evidence purpose and misuse boundary. A correlation heatmap,
  pooled mean or similarity ranking must not silently become a causal effect, fair group comparison
  or identity conclusion.
- Freeze a data-audit artifact that downstream scripts consume.
- Verify key counts, transformations, formulas, reconciliation and artifact hashes through a route
  independent of the main audit implementation. Independent recomputation checks implementation
  consistency; it does not replace human review of the methodology.

Exit only when each task has an explicit data interface, every material data defect has a documented
treatment or unresolved-risk status, the method/implementation mismatch audit passes, and the user
has accepted treatments that can alter downstream results.

Read `16-data-audit-methodology.md` before planning or implementing this stage, and
`04-figure-generator.md` when producing its figures.

### Stage 4 — EVIDENCE AND DESIGN

Goal: compare defensible mathematical routes and commit to a testable specification.

Before proposing the active question's baseline or model family, execute the per-question literature
orientation gate in `08-literature-search.md`. This gate is mandatory when the team lacks the
application-domain background, auxiliary variables or mechanisms need interpretation, external
claims will enter the problem background or analysis, or model assumptions, parameters, metrics and
validation require outside evidence. A literature-free exception must state why the question is
fully determined by the statement and data.

- Search official rules first, then primary papers, authoritative books, and verified domain data.
- Record title, authors, year, DOI/original URL, access date, reading status, supported claim, and
  limitation.
- Do not collect references merely to increase count.
- Search iteratively: first to identify method families, then to resolve assumptions, metrics,
  parameter ranges, validation design, and applicability discovered during formulation.
- For each task, compare at least two plausible approaches when alternatives genuinely exist. Explain:

- reality object to mathematical object mapping;
- variables, parameters, objective, constraints, and constraint counterfactuals;
- why the model fits the question better than the alternatives;
- how candidate solutions will be formed and compared;
- what will prove feasibility, optimality, robustness, and applicability.

Build and preserve the forward evidence chain:

`statement and official data → subproblem analysis → method specification → code implementation
→ frozen outputs → paper`.

The subproblem analysis and method specification are not informal notes written after coding. They
are the design authority for the implementation: each stated requirement, decision object,
objective, constraint, assumption, validation criterion, and expected output must have an explicit
downstream realization. Before coding, audit both explicit task requirements and implicit
executability requirements. For each implicit requirement, decide with evidence whether it is
mandatory, a realism enhancement, or outside the intended scope; do not silently omit it merely
because the statement does not name it.

First determine the modeling sequence and dependency graph; only then derive section headings.

Define before coding: a simple or reality-based baseline, acceptance tests, independent verification
route, sensitivity risks, expected figures/tables, and the claims the task is allowed to support.

For multi-question problems, do not assume that every question must pass through baseline design,
model comparison, specification and implementation in horizontal lockstep. If the questions use
different mathematical mechanisms, the user reports cognitive overload, or later questions depend
on earlier results, switch to one-question vertical slices. Keep shared source, terminology and data
work global, then discuss only the active question's evidence, baseline, alternatives and decisions.
Do not ask the user to pre-decide later-question models, parameters or experimental-design policies
merely because the project has reached a globally named stage.

Apply a question-independence gate before proposing each later question's method. Start from that
question's own object, action, quantifiers, required output, data structure, comparison unit and
failure risk; do not use the previous question's model, validation pattern, figure set or prose
sequence as the default candidate. Ask the counterfactual: “If the previous question and its code
did not exist, would this method still be selected for the current question?” If unclear, regenerate
the candidate set from the current task.

Classify every proposed inheritance as a shared compatible fact or data interface, a verified
upstream conclusion explicitly required here, a method component independently justified for the
current question, or a prior-question artifact retained only by workflow or coding inertia. Require
a direct map from every retained method component to a current-question output or material risk.
Remove components that only make questions look uniform, repeat an upstream summary without a new
role, or require artificial validation operations to preserve an inherited model. Design robustness
around the current data's real blocks, dependencies, constraints and claim failure modes; do not
force the previous question's deletion, perturbation or fitting pattern onto a different unit.

Deep-interaction gate: show what the evidence changes, then present model alternatives, tradeoffs,
assumptions, expected outputs, and
verification plan. Wait for user approval before implementing a materially different model family.

Exit with synchronized reference records and `planning/method_plan.md`, including the code/output/
claim dependency graph.

Read `07-algorithm-reference.md`, `08-literature-search.md`, `09-robustness-checker.md`,
`12-source-audit-and-provenance.md`, and relevant portions of `03-paper-content-rules.md`.

### Stage 5 — SOLVE PER SUBPROBLEM

Goal: finish one vertically complete, reviewable slice before moving to its dependents.

Process tasks in dependency order. For each task execute:

`specify → hand-check → implement → solve → independently verify → interpret → freeze → review`

When using one-question vertical slices, expand the slice to:

`question-specific statement/data facts → literature orientation → evidence review → baseline
→ candidate methods → human decision → specify → hand-check → implement → solve
→ independently verify → stress → interpret → freeze → review`

Keep only one question's material decisions open at a time unless the user explicitly requests a
cross-question comparison. Reuse compatible approved decisions and shared data without reopening
them, and defer unrelated later-question choices until their slice begins.

At the start of every slice, record its necessary independence from previous slices: what is
inherited, why it remains compatible, what is deliberately not inherited, and how the selected
method answers this question even if earlier method artifacts are hidden. Cross-question consistency
means compatible facts and interfaces agree; it does not mean methods, formulas, validation tests
or section structures must look alike.

- Put shared parsing, units, graph, and plotting logic in `src/_utils/`.
- Give each conclusion-producing script exact `# 输入:` and `# 输出:` headers.
- Freeze every conclusion in structured output; stdout is diagnostic only.
- Derive results from inputs; never write a previous result back as a model constant.
- Keep question facts, analysis settings, derived results, and presentation constants distinct.
- Run small hand checks before full optimization.
- Recompute constraints and headline metrics from the final decision with code independent of the
  optimizer summary. Add a baseline or counterfactual that exposes what the model contributes.
- Write the task's claim-ledger entries with scope, conditions, evidence path, verification status
  and forbidden extrapolation.
- Do not force a fixed number of models, variables, figures or sensitivity parameters. Require only
  artifacts that answer a task or test a material risk.

After each task, show the user the mathematical result, the evidence path, surprising behavior, and
remaining uncertainty. Do not hide behind solver status or engineering reproduction detail.

Exit each task only when its scripts compile, declared inputs exist, outputs are frozen, acceptance
tests pass, and downstream tasks know the exact upstream artifact version. A failed task does not
invalidate independent completed tasks.

Read `10-json-handoff.md`, `09-robustness-checker.md`, and
`12-source-audit-and-provenance.md`.

### Stage 6 — INTEGRATE AND ATTACK

Goal: challenge the assembled solution and its cross-task consistency.

- Recompute metrics from final decisions rather than reusing model summaries.
- Use enumeration, bounds, matching equivalence, conservation, perturbation, alternative
  formulations, or counterexamples as appropriate.
- State exactly what each check proves and what it does not prove.
- Freeze verification results and ensure paper claims do not exceed them.
- When a paper review or user question exposes a possible defect, trace it backward through outputs,
  code, method documents, subproblem analysis, statement, and data. Classify it as a communication
  omission, implementation/specification mismatch, or modeling omission before choosing a fix.
- A suspected modeling omission must receive an impact audit: identify affected feasibility,
  optimality, executability, and conclusions; construct a counterexample or diagnostic when
  possible; then compare the current solution with a corrected or strengthened formulation.
- Do not repair a modeling or implementation defect only by weakening or expanding paper prose.
  Correct the earliest faulty layer, regenerate every downstream artifact, and then revise the
  paper.
- Check task inheritance: later tasks must consume the intended version of upstream results, preserve
  or explicitly replace assumptions, units, symbols and evaluation criteria, and distinguish
  re-optimization from evaluation of a fixed solution.
- Run change-impact analysis. Any change to interpretation, data, assumption, model, parameter or
  output requires reviewing its downstream dependents; record this only at the detail needed to
  prevent stale conclusions.

Deep-interaction gate: report failed checks, fragile assumptions, and boundary cases before revising
the model. Do not silently tune parameters to hide failures.

Exit when each headline conclusion has an evidence-backed verification status.

Read `05-audit-protocol.md` and `09-robustness-checker.md`.

### Stage 7 — STRESS, EVALUATE AND GENERALIZE

Goal: determine where the verified solution remains useful and where it fails.

- Select uncertainty and stress tests from the claim ledger and risk register, not from a generic
  percentage grid.
- Separate input uncertainty, structural uncertainty, algorithmic randomness, scenario change,
  threshold policy and model misspecification.
- Report feasibility, decision stability, objective change, constraint violations, uncertainty
  intervals and failure boundaries as appropriate.
- Evaluate strengths only against demonstrated baselines or structural properties. State limitations
  as omitted mechanisms plus likely consequence and trigger for model extension.
- Generalize by mapping invariant mathematical structure, required data and changed assumptions;
  do not rename the same model as universal.

Exit when every major claim has an applicability statement and material risks have been tested,
bounded, or explicitly left unresolved.

### Stage 8 — COMMUNICATE

Goal: write a paper whose mathematics can be reconstructed by a reader.

- Build the paper from verified outputs, not memory or console text.
- Before judging, introducing, shortening, or replacing any term, locate the project's current
  authority map and unique terminology source, normally `planning/README.md` and
  `planning/terminology.md`, and read the applicable definition completely. Treat the abstract,
  symbol table, body wording, code names, and majority usage as consistency targets rather than
  authorities. If no unique terminology source exists, propose one and obtain user approval before
  promoting terminology into evaluator-visible text; never infer the preferred term by counting
  occurrences.
- Treat the paper as the evaluator-visible, self-contained synthesis. Material that exists only in
  `planning/`, `docs/`, code comments, console output, or chat is not communicated evidence.
- Treat abstract--body--result tracking as a bidirectional evidence-chain audit, not as a
  one-file authority check. Compare the statement and approved task definition, method
  specification, mathematical expressions, implementation, frozen outputs, figures and tables,
  body text, abstract, and conclusion. No single occurrence may be used by itself to overwrite the
  others. When they disagree, identify the earliest layer that is unsupported or incorrect, repair
  it there, and propagate the accepted correction through every dependent artifact.
- Apply “fix once, fix everywhere” even to terminology-only or explanatory changes: search all
  full names, abbreviations, synonyms, related conditions, and linked numbers across the project,
  then synchronize the abstract, first body definition, formula explanation, table headers,
  captions, result discussion, conclusion, claim map, current audit, reproduction documents, and
  delivery copy. A mismatch is not closed merely because the sentence that exposed it was fixed.
- For each question, write problem and model, concrete build steps, solve logic, important results,
  validation, sensitivity, and applicability.
- Explain every formula, symbol, parameter source, objective order, and stopping or optimality
  argument.
- Make the problem-analysis opening explain why the statement groups its tasks as it does and how
  later subproblems inherit, alter, or extend earlier objects, criteria, and results. For each
  subproblem, identify its recognized problem family, summarize the principal method families used
  for such problems, and then motivate the paper's choice in accessible language.
- Treat unexplained abstraction as a defect. A technical label, priority level, tolerance,
  weighting rule, or claimed innovation must be tied to its mathematical action, parameter source,
  concrete effect on a solution, and practical meaning; when feasible, show a small worked example
  or stage-by-stage comparison.
- Give each figure and table a unique information role; describe relation, phenomenon, conclusion,
  and decision use.
- Before polishing a question, build a “task claim—primary evidence—necessary boundary” map.
  Assign one primary carrier to each claim and retain secondary diagnostics only when they test a
  distinct failure risk. Keep reproducible auxiliary metrics in structured outputs or technical
  documentation instead of making every computed statistic compete in the manuscript narrative.
- Keep the abstract specific: problem, mechanism, solution path, result, and verification for every
  major task, while preserving the required page limit.
- Treat defects exposed by abstract revision as candidates for manuscript-wide rules. After an
  abstract audit, extract reusable requirements concerning explicit objects, closed actions,
  metric definitions, baselines, conditions, result provenance, claim strength, and concept
  hierarchy; then audit the body, figures, tables, and conclusion at the information density
  appropriate to each section. Do not mechanically expand every sentence: preserve ordinary
  back-reference when the antecedent is unique and nearby, and distinguish a semantic gap from a
  merely possible stylistic rewrite.
- Assemble the paper in the reader's order, not the execution directory's order:
  restatement → problem analysis → assumptions and symbols → per-task model/build/solve/result/check
  → integrated evaluation and applicability → conclusion → references and required appendices.
- Maintain a bidirectional map between paper claims and the claim ledger. A technically completed
  artifact that is absent from the paper is not evaluator-visible evidence.

Use the official template if provided. Never let a generic style rule override an official file.

Read `02-latex-setup.md`, `03-paper-content-rules.md`, `04-figure-generator.md`,
`06-weiwei-norms.md`, `11-paper-finalizer.md`, and
`13-excellent-paper-expression.md`. Use the latter to learn transferable sentence functions
from public excellent papers without copying their wording or inheriting their defects. Before
rewriting evaluator-visible prose, execute its “逐句因果闭合检查”: place a real reason next to
each substantive judgment, explain the problem-specific mechanism before naming the technical
term, and bind every proof claim to the candidate domain, constraints, comparison, or test that
supports it.

### Stage 9 — AUDIT AND SUBMIT

Goal: produce a traceable final delivery.

- Audit rule by rule and file by file: statement, sources, code, outputs, docs, references, paper,
  figures, PDF, logs, mirrors, and archives.
- Audit figures and tables at three levels: manuscript-wide completeness and appropriate choice of
  visual/table/text carrier; per-artifact content correctness and evidentiary function; and
  rendering, legibility, layout, and accessibility quality. Passing one level never compensates for
  failing another.
- Rerun the entire pipeline from official input.
- Compile the paper and visually inspect every page, not only the log.
- Check abnormal whitespace, float drift, table consistency, figure readability, citation
  completeness, numeric traceability, and appendix/source agreement.
- Update hashes, work log, unresolved issues, and delivery mirrors.
- Update `HANDOFF.md` after final audit, material rollback, changed applicability, or a new pause point.
- Resolve stale, missing, invalidated, or orphaned artifacts before packaging. Use scripts for
  mechanical checks when useful, but do not substitute automation for substantive review.

Exit only with a written final audit that distinguishes passed, fixed, and intentionally unresolved
items.

For a milestone or final audit, execute the full-read gate and read every numbered module so that
cross-module obligations are not hidden by routing. Routing still determines which module owns each
repair; it does not permit a partial project or skill review at closure.

## Interaction protocol

The user wants deep collaboration, not a silent one-shot solution.

- At the start of each substantial stage, explain what will be examined, why it matters, and which artifacts will
  be produced.
- Calibrate explanations to the team's stated foundation. For weak-foundation teams, maintain a
  plain-language reader layer alongside the technical layer and use a small worked example before
  presenting project-specific statistics or model outputs.
- Before a material assumption or model-family choice, present evidence, alternatives, consequences,
  and a recommendation.
- When the user raises a conceptual doubt, inspect the statement, mathematics, code, and outputs
  before answering.
- Separate proposal from mutation: if the user asks for an audit or plan first, do not implement
  until approved.
- Record substantive decisions in `planning/interaction_log.md`; distinguish AI proposal, user
  decision, accepted scope and resulting artifacts. Do not rely on chat history alone.
- Continue autonomously only on reversible, already-approved implementation details; return to the
  user when a choice changes modeled reality, evaluation criteria, mathematical specification,
  claimed conclusion or delivery scope.

## Directory and file creation rules

- Never overwrite original inputs.
- Never create question-specific code before Stage 4 has an approved plan.
- Never create a polished paper before verified outputs exist; an empty template may be prepared only
  after official formatting rules are known.
- Create only files with a declared role and producer/consumer.
- Keep temporary renders and caches outside the project or exclude them from delivery.
- Do not package stale mirrors. The main project is authoritative until hashes prove synchronization.

## Reference router

Read each referenced file completely when its trigger applies:

| File | Load when | Not responsible for |
|---|---|---|
| `01-contest-project-pattern.md` | Establishing project/code/output conventions | Detailed prose or final acceptance |
| `02-latex-setup.md` | Building the sole LaTeX manuscript, applying the official template, compiling, and checking page layout | Deciding manuscript content, designing figure semantics, or approving the final submission package |
| `03-paper-content-rules.md` | Writing or revising manuscript content | Certifying that the paper passes |
| `04-figure-generator.md` | Designing figures or tables | Whole-paper language review |
| `05-audit-protocol.md` | Auditing evidence, content, language, or rendering | Generating the first draft |
| `06-weiwei-norms.md` | Applying or auditing the classified citation, style, structure, formula, visual, and support-material rules derived from the named lecture | Inferring force from the lecture source rather than each rule's A–E label |
| `07-algorithm-reference.md` | Comparing covered algorithm families | Serving as literature evidence |
| `08-literature-search.md` | Searching, selecting, and recording evidence | Setting citation placement |
| `09-robustness-checker.md` | Designing validation, sensitivity, or uncertainty tests | Generic final-paper checking |
| `10-json-handoff.md` | Building reproducible multi-script outputs | Session or manuscript handoff |
| `11-paper-finalizer.md` | Assembling and approving the submission package | Rewriting content or audit rules |
| `12-source-audit-and-provenance.md` | Sources, rule hierarchy, AI records, feedback migration | Direct paper wording |
| `13-excellent-paper-expression.md` | Applying or auditing its classified expression, evidence-chain, model-explanation, result, and claim-strength rules | Treating every observed paper pattern as mandatory |
| `14-session-handoff.md` | Recovering or checkpointing project state | Machine artifact lineage |
| `15-pipeline-methodology.md` | Cross-stage dependencies and feedback propagation | Detailed implementation rules |

## Failure conditions

Stop and report rather than improvise when:

- an original file cannot be read or its provenance is uncertain;
- the task statement and attachment conflict;
- a missing condition changes the answer and the user has not selected an interpretation;
- a result cannot be reproduced from frozen outputs;
- validation contradicts the paper;
- a proposed task number, next question, code path, or paper heading cannot be traced to the
  original statement, or the statement, task matrix, and paper structure disagree about it;
- formal submission would require disclosure or identity materials that do not exist.
