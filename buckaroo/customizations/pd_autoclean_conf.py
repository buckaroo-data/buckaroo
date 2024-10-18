from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.pandas_commands import (
    SafeInt, DropCol, MakeCategory, FillNA, Rank,
    DropDuplicates, GroupBy, GroupByTransform, RemoveOutliers, OnlyOutliers, Search, SearchCol,
    LinearRegression)

from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)

BASE_COMMANDS = [
    #Basic Column operations
    DropCol, FillNA, MakeCategory,

    #Cleaning Operations
    DropDuplicates, SafeInt, 

    #Column modifications
    Rank,

    #Filtering ops
    RemoveOutliers, OnlyOutliers,
    Search, SearchCol, 

    #complex transforms
    GroupBy, GroupByTransform,
    LinearRegression
]


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
    quick_command_klasses = []
    name="default"

class NoCleaningConf(AutocleaningConfig):
    #just run the interpreter
    autocleaning_analysis_klasses = []
    command_klasses = BASE_COMMANDS
    quick_command_klasses = [Search]
    name="NoCleaning"

