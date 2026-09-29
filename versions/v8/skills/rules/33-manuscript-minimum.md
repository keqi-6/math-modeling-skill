# Manuscript quality

Apply this file only when the controller permits evaluator-visible work.

## Whole-paper chain

For every question make the following findable:

`problem conflict → method choice and alternative → object mapping → assumptions and variables →
formula or algorithm → result → validation → direct answer → boundary`

Within that chain, validation must include at least one substantive model examination per question.

The paper must carry its own reasoning. Planning notes, chat, code comments, and logs do not
substitute for evaluator-visible evidence.

## Reader-first explanation

- Introduce a necessary term with ordinary language, formal name, project mapping, and role.
- Remove a term that does not change a decision, ensure reproducibility, prevent distortion, or
  support a source.
- Before formulas and results, explain the real difficulty, why the simple approach is insufficient,
  how the selected method addresses it, the important alternative, output, and limit.
- Use a minimal example when an abstract operation cannot otherwise be replayed by an ordinary
  reader.
- Apply the masking test: after hiding model names, formulas, and result numbers, the remaining prose
  must still explain the problem, method action, reason, output, and boundary.

## Sections

- Title: cover the real object and tasks without overstating capability.
- Abstract: for each task give method action, role, result meaning, and necessary boundary; avoid a
  list of method names and numbers.
- Background: establish the real conflict and why the requested quantities matter; do not preview
  the solution.
- Restatement: preserve quantifiers, strict inequalities, scenarios, and deliverables.
- Problem analysis: use `difficulty → available structure → method directions → selection reason →
  output and boundary`; keep formulas and implementation details later.
- Assumptions: retain only conditions not given directly by the statement and necessary for the
  method.
- Symbols: include used symbols with stable meanings and units.
- Results: identify object, baseline, metric, direction, magnitude, mechanism supported by evidence,
  exception, and task implication.
- Evaluation: pair each strength and limitation with concrete evidence and consequence.
- Conclusion: answer the tasks in order without introducing new methods or claims.
- References: cite the nearby external fact or method claim with verified metadata.

Model examination: for every question show at least one test with substantive information gain,
including its object or mathematical relation, criterion, result, and proof boundary. Hashes,
field reconciliation, or repeated implementation agreement do not satisfy this minimum. The test
may remain adjacent to the model or result; do not force a section named “model validation”.

## Consistency and style

- Keep terminology, units, precision, condition, and claim strength stable across abstract, body,
  figures, conclusion, code, and outputs.
- Place conditions and non-extrapolation boundaries next to the claim they limit.
- Avoid template filler, fake causality, unexplained abbreviations, stacked parentheses, and
  engineering details in the reasoning line.
- Read the entire manuscript continuously after local edits and propagate general defects globally.
