from buckaroo.pluggable_analysis_framework.pluggable_analysis_framework import ColAnalysis
from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.pandas_commands import (
    DropCol, MakeCategory, FillNA, Rank,
    DropDuplicates, GroupBy, GroupByTransform, RemoveOutliers, OnlyOutliers, Search, SearchCol,
    LinearRegression)

from buckaroo.customizations.analysis import (
    DefaultSummaryStats, PdCleaningStats)
from buckaroo.customizations.pd_fracs import HeuristicFracs, AggresiveCleaningGenOps, ConvservativeCleaningGenops
from buckaroo.customizations.pandas_cleaning_commands import (
    IntParse,
    StrBool,
    USDate,
    StripIntParse
)

from buckaroo.customizations.pandas_commands import (
    NoOp,
)


#all commands used need to be in base_commands for the configuration of the lowcode UI
BASE_COMMANDS = [
    #Basic Column operations
    DropCol, FillNA, MakeCategory,

    #Cleaning Operations
    DropDuplicates,
    IntParse, StripIntParse,
    StrBool, USDate,
    

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
    name=""



class AggressiveAC(AutocleaningConfig):
    autocleaning_analysis_klasses = [HeuristicFracs, AggresiveCleaningGenOps]
    command_klasses = [
        IntParse,
        StripIntParse,
        StrBool,
        USDate,
        DropCol,
        FillNA,
        GroupBy,
        NoOp,
        Search,
    ]

    quick_command_klasses = [Search]
    name = "aggressive"


class ConservativeAC(AggressiveAC):
    autocleaning_analysis_klasses = [
        HeuristicFracs,
        ConvservativeCleaningGenops,
    ]
    name = "conservative"

