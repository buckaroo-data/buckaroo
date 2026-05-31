"""Stable import location for ColAnalysis.

The v1 DAG-ordering helpers that used to live here (``order_analysis``,
``check_solvable``) have been removed — typed_dag.py now handles ordering and
solvability for stat functions. ``ColAnalysis`` itself lives in
``col_analysis``; this module re-exports it for existing import sites.
"""
from .col_analysis import ColAnalysis  # noqa: F401
