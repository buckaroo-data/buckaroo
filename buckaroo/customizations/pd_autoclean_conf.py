from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.pandas_commands import (
    SafeInt, DropCol, FillNA, GroupBy, RemoveOutliers, OnlyOutliers, Search)

from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)

BASE_COMMANDS = [DropCol, FillNA, GroupBy, SafeInt, RemoveOutliers, OnlyOutliers, Search]


class CleaningGenOps(ColAnalysis):
    requires_summary = ['int_parse_fail', 'int_parse']
    provides_defaults = {'cleaning_ops': []}

    int_parse_threshhold = .3
    @classmethod
    def computed_summary(kls, column_metadata):
        if column_metadata['int_parse'] > kls.int_parse_threshhold:
            return {'cleaning_ops': [{'symbol': 'safe_int', 'meta':{'auto_clean': True}}, {'symbol': 'df'}]}
        else:
            return {'cleaning_ops': []}

class CleaningConf(AutocleaningConfig):
    autocleaning_analysis_klasses = [DefaultSummaryStats, CleaningGenOps, PdCleaningStats]
    command_klasses = BASE_COMMANDS
    name="default"

class NoCleaningConf(AutocleaningConfig):
    #just run the interpreter
    autocleaning_analysis_klasses = []
    command_klasses = BASE_COMMANDS
    name="NoCleaning"

