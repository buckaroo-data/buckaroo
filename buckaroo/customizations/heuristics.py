from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import (
    ColAnalysis)
from buckaroo.jlisp.lisp_utils import sA
from buckaroo.auto_clean.heuristic_lang import get_top_score


class BaseHeuristicCleaningGenOps(ColAnalysis):
    """
    This class is meant to be extended with different rules passed in

    create other ColAnalysis classes that satisfy requires_summary

    Then put this group of classes into their own AutocleaningConfig

    The important thing is that this class returns "cleaning_ops"
    """

    requires_summary = []
    provides_defaults = {"cleaning_ops": []}

    rules = {}
    rules_op_names = {}

    @classmethod
    def computed_summary(kls, column_metadata):
        cleaning_op_name = get_top_score(kls.rules, column_metadata)
        if cleaning_op_name == "none":
            return {"cleaning_ops": [], "cleaning_name": "None"}
        else:
            cleaning_name = kls.rules_op_names.get(
                cleaning_op_name, cleaning_op_name
            )
            ops = [
                sA(
                    cleaning_name,
                    clean_strategy=kls.__name__,
                    clean_col=column_metadata["col_name"],
                ),
                {"symbol": "df"},
            ]
            return {
                "cleaning_ops": ops,
                "cleaning_name": cleaning_name,
                "add_orig": True,
            }
