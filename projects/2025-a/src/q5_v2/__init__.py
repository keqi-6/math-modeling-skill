"""Q5_v2 objective and decomposition utilities.

The original :mod:`src.q5` implementation remains unchanged.  Q5_v2 starts by
making interval aggregation and objective semantics explicit before adding a
new master solver.
"""

from .objectives import (
    ObjectiveMetrics,
    from_interval_sets,
    from_q5_evaluation,
    intersect_many,
    interval_measure,
    lexicographic_better,
    normalize_intervals,
    pareto_dominates,
)

__all__ = [
    "ObjectiveMetrics",
    "from_interval_sets",
    "from_q5_evaluation",
    "intersect_many",
    "interval_measure",
    "lexicographic_better",
    "normalize_intervals",
    "pareto_dominates",
]
