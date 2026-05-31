from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.pandas_commands import (
    DropCol, MakeCategory, FillNA, Rank,
    DropDuplicates, GroupBy, GroupByTransform, RemoveOutliers, OnlyOutliers, Search, SearchCol,
    ToDatetime, LinearRegression)

from buckaroo.customizations.pd_stats_v2 import (
    PD_AUTOCLEAN_DEFAULT_V2, PD_AUTOCLEAN_AGGRESSIVE_V2, PD_AUTOCLEAN_CONSERVATIVE_V2)
from buckaroo.customizations.pandas_cleaning_commands import (
    IntParse,
    StrBool,
    USDate,
    StripIntParse
)

from buckaroo.customizations.pandas_commands import (NoOp)


#all commands used need to be in base_commands for the configuration of the lowcode UI
BASE_COMMANDS = [
    #Basic Column operations
    DropCol, FillNA, MakeCategory,

    #Cleaning Operations
    DropDuplicates,
    IntParse, StripIntParse,
    StrBool, USDate,
    ToDatetime,
    

    #Column modifications
    Rank,

    #Filtering ops
    RemoveOutliers, OnlyOutliers,
    Search, SearchCol, 

    #complex transforms
    GroupBy, GroupByTransform,
    LinearRegression]


class CleaningConf(AutocleaningConfig):
    autocleaning_analysis_klasses = PD_AUTOCLEAN_DEFAULT_V2
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
    autocleaning_analysis_klasses = PD_AUTOCLEAN_AGGRESSIVE_V2
    command_klasses = [IntParse, StripIntParse, StrBool, USDate, DropCol, FillNA, GroupBy, NoOp, Search]

    quick_command_klasses = [Search]
    name = "aggressive"


class ConservativeAC(AggressiveAC):
    autocleaning_analysis_klasses = PD_AUTOCLEAN_CONSERVATIVE_V2
    name = "conservative"

