"""Type-level cases for init_sd and column config typing (#978).

Not collected by pytest. basedpyright checks this file through
pyrightconfig.typecheck.json: each line carrying a ``# pyright: ignore[...]``
is a mistake the types have to reject, and reportUnnecessaryTypeIgnoreComment
turns an ignore that no longer suppresses anything into an error.

Widget and dataflow constructors aren't exercised here. They're traitlets
HasTraits classes, whose ``__new__`` returns Any, so pyright never checks
the arguments of a ``BuckarooWidget(...)`` call against ``__init__``.
"""
from typing import List

import pandas as pd
import polars as pl

from buckaroo.dataflow.styling_core import DisplayerArgs, InitSD, OverrideColumnConfig, PinnedRowConfig
from buckaroo.server.data_loading import create_dataflow
from buckaroo.server.data_loading_polars import create_polars_dataflow

# display config and summary stats share an init_sd entry
INIT_SD: InitSD = {
    'comments': {
        'displayer_args': {'displayer': 'string', 'max_length': 2000},
        'ag_grid_specs': {'wrapText': True, 'autoHeight': True, 'width': 400},
        'delete_keys': ['tooltip_config'],
        'highlight_phrase': ['refund', 'late'],
        'highlight_color': 'orange',
        'column_config_override': {'tooltip_config': {'tooltip_type': 'simple', 'val_column': 'comments'}},
        'mean': 3.5,
        'dtype': 'object'},
    'membership': {'merge_rule': 'hidden'},
    # displayer_args is merged over the computed one, so a partial dict is fine
    'notes': {'displayer_args': {'max_length': 500}}}

BAD_AG_GRID_SPECS: InitSD = {'comments': {'ag_grid_specs': 'wrapText'}}  # pyright: ignore[reportAssignmentType]
# a str is an Iterable[str], so an Iterable-typed delete_keys would accept this and drop nothing
BAD_DELETE_KEYS: InitSD = {'comments': {'delete_keys': 'tooltip_config'}}  # pyright: ignore[reportAssignmentType]
BAD_DISPLAYER_ARGS: InitSD = {'comments': {'displayer_args': 'string'}}  # pyright: ignore[reportAssignmentType]
TYPO_DISPLAYER_ARGS: InitSD = {'comments': {'displayer_args': {'max_lenght': 2000}}}  # pyright: ignore[reportAssignmentType]
BAD_HIGHLIGHT: InitSD = {'comments': {'highlight_color': 3}}  # pyright: ignore[reportAssignmentType]
BAD_MERGE_RULE: InitSD = {'membership': {'merge_rule': 'hiden'}}  # pyright: ignore[reportAssignmentType]


def init_sd_entry_point_cases(df: pd.DataFrame, pl_df: pl.DataFrame) -> None:
    create_dataflow(df, init_sd=INIT_SD)
    create_polars_dataflow(pl_df, init_sd=INIT_SD)
    create_dataflow(df, init_sd={'comments': {'ag_grid_specs': 'wrapText'}})  # pyright: ignore[reportArgumentType]
    create_polars_dataflow(pl_df, init_sd={'comments': {'ag_grid_specs': 'wrapText'}})  # pyright: ignore[reportArgumentType]


# merge_rule on its own is a whole override (compare.py, extension_utils.py)
OVERRIDES: OverrideColumnConfig = {
    'membership': {'merge_rule': 'hidden'},
    'price': {'color_map_config': {'color_rule': 'color_map', 'map_name': 'BLUE_TO_YELLOW'}}}
BAD_OVERRIDE: OverrideColumnConfig = {'membership': {'merge_rule': 'hiden'}}  # pyright: ignore[reportAssignmentType]

# displayers and displayer keys the JS side has that the Python types were missing
PINNED: List[PinnedRowConfig] = [
    {'primary_key_val': 'mean', 'displayer_args': {'displayer': 'inherit'}},
    {'primary_key_val': 'elapsed', 'displayer_args': {'displayer': 'duration'}}]
HIGHLIGHTED: DisplayerArgs = {
    'displayer': 'string', 'max_length': 35, 'highlight_phrase': ['refund', 'late'], 'highlight_color': 'orange'}
