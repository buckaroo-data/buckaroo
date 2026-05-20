from buckaroo.dataflow.autocleaning import AutocleaningConfig
from buckaroo.customizations.xorq_commands import (
    DropCol, DropDuplicates, FillNA, NoOp, Search)


XORQ_BASE_COMMANDS = [DropCol, DropDuplicates, FillNA, NoOp, Search]


class NoCleaningConfXorq(AutocleaningConfig):
    """No automatic cleaning — just expose the interpreter and quick-search.

    The autocleaning analysis classes are pandas-flavoured (HeuristicFracs,
    PdCleaningStats, ...) and would not work against ibis exprs, so we
    leave the analysis list empty. The lisp interpreter still runs against
    the expression via the ported xorq_commands, and the frontend's
    quick-search box drives the Search command.
    """

    autocleaning_analysis_klasses = []
    command_klasses = XORQ_BASE_COMMANDS
    quick_command_klasses = [Search]
    name = ""
