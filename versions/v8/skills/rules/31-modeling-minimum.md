# Modeling quality

Apply this file only within the action permissions of `S2` through `S5`. The controller alone
decides whether a method may be promoted or implemented.

## Assessment and selection

- Translate the task into the quantities, decisions, comparisons, and boundaries it actually asks
  for.
- Start with a simple baseline that can be checked by hand.
- Identify the precise failure or insufficiency of the baseline before adding complexity.
- Compare methods by question fit, assumptions, identifiability, outputs, validation, failure risk,
  interpretability, and downstream cost.
- Treat “no method change” as a real option.
- Do not equate official examples, popularity, novelty, or a better internal metric with necessity.

## Mathematical specification

For an approved method, freeze:

- real objects and their mathematical representation;
- indices, variables, units, domains, and statistical level;
- assumptions and the consequence if each fails;
- objectives, constraints, relationships, and parameter sources;
- candidate or search domain;
- expected outputs and acceptance tests;
- statements the method cannot support.

Explain each major construction as `object → relation → formula → role`. Introduce auxiliary
variables and constraints only when their necessity is demonstrated. For multi-objective work,
state priority, scale, trade-off meaning, tie handling, tolerance, and what changes when an objective
is added.

## Solving and results

- Explain candidate generation, comparison, stopping, feasibility handling, and reconstruction of
  the answer; software names are not algorithmic explanations.
- Keep code, formula, parameters, and frozen outputs identical in meaning.
- Present results as baseline, change, cause or mechanism supported by the model, cost or exception,
  and decision meaning.
- Do not turn a candidate-domain optimum into a continuous or real-world global optimum.
- End every question with a direct ordinary-language answer and its applicability boundary.

