from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.polars_commands import (
    Search)




class NoCleaningConfPl(AutocleaningConfig):
    #just run the interpreter
    autocleaning_analysis_klasses = []
    command_klasses = [Search]
    quick_command_klasses = [Search]
    name="NoCleaning"

