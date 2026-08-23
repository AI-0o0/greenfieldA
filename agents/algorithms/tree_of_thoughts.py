"""Alias for algorithms.tree_of_thought to support both singular and plural module names."""
from .tree_of_thought import (
    ThoughtCandidates,
    ThoughtEvaluation,
    tree_of_thoughts,
    run_tree_of_thoughts,
)

__all__ = [
    "ThoughtCandidates",
    "ThoughtEvaluation",
    "tree_of_thoughts",
    "run_tree_of_thoughts",
]
