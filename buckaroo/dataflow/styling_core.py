import copy
import logging
from typing import Iterable, TypedDict, Union, List, Dict, Any, Literal
from typing_extensions import NotRequired, TypeAlias

import pandas as pd
from buckaroo.df_util import ColIdentifier, old_col_new_col, to_chars
from buckaroo.pluggable_analysis_framework.col_analysis import (ColAnalysis, ColMeta, SDType)

logger = logging.getLogger()

# Cell Renderer Types
HistogramDisplayerA = TypedDict('HistogramDisplayerA', {'displayer': Literal["histogram"]})
ChartDisplayerA = TypedDict('ChartDisplayerA', {'displayer': Literal["chart"]})
LinkifyDisplayerA = TypedDict('LinkifyDisplayerA', {'displayer': Literal["linkify"]})
BooleanCheckboxDisplayerA = TypedDict('BooleanCheckboxDisplayerA', {'displayer': Literal["boolean_checkbox"]})
Base64PNGImageDisplayerA = TypedDict('Base64PNGImageDisplayerA', {'displayer': Literal["Base64PNGImageDisplayer"]})
SVGDisplayerA = TypedDict('SVGDisplayerA', {'displayer': Literal["SVGDisplayer"]})

CellRendererArgs = Union[
    HistogramDisplayerA,
    ChartDisplayerA,
    LinkifyDisplayerA,
    BooleanCheckboxDisplayerA,
    Base64PNGImageDisplayerA,
    SVGDisplayerA
]

# Formatter Types
ObjDisplayerA = TypedDict('ObjDisplayerA', {
    'displayer': Literal["obj"],
    'max_length': NotRequired[int]
})

BooleanDisplayerA = TypedDict('BooleanDisplayerA', {
    'displayer': Literal["boolean"]
})

StringDisplayerA = TypedDict('StringDisplayerA', {
    'displayer': Literal["string"],
    'max_length': NotRequired[int]
})

FloatDisplayerA = TypedDict('FloatDisplayerA', {
    'displayer': Literal["float"],
    'min_fraction_digits': int,
    'max_fraction_digits': int
})

DatetimeDefaultDisplayerA = TypedDict('DatetimeDefaultDisplayerA', {
    'displayer': Literal["datetimeDefault"]
})

DatetimeLocaleDisplayerA = TypedDict('DatetimeLocaleDisplayerA', {
    'displayer': Literal["datetimeLocaleString"],
    'locale': Literal["en-US", "en-GB", "en-CA", "fr-FR", "es-ES", "de-DE", "ja-JP"],
    'args': Dict[str, Any]
})

IntegerDisplayerA = TypedDict('IntegerDisplayerA', {
    'displayer': Literal["integer"],
    'min_digits': int,
    'max_digits': int
})

FormatterArgs = Union[
    ObjDisplayerA,
    BooleanDisplayerA,
    StringDisplayerA,
    FloatDisplayerA,
    DatetimeDefaultDisplayerA,
    DatetimeLocaleDisplayerA,
    IntegerDisplayerA
]

# Combined displayer types
DisplayerArgs = Union[FormatterArgs, CellRendererArgs]

# Color mapping types
ColorMap = Union[Literal["BLUE_TO_YELLOW", "DIVERGING_RED_WHITE_BLUE"], List[str]]

ColorMapRules = TypedDict('ColorMapRules', {
    'color_rule': Literal["color_map"],
    'map_name': ColorMap,
    'val_column': NotRequired[str]
})

ColorCategoricalRules = TypedDict('ColorCategoricalRules', {
    'color_rule': Literal["color_categorical"],
    'map_name': ColorMap,
    'val_column': NotRequired[str]
})

ColorWhenNotNullRules = TypedDict('ColorWhenNotNullRules', {
    'color_rule': Literal["color_not_null"],
    'conditional_color': Union[str, Literal["red"]],
    'exist_column': str
})

ColorFromColumn = TypedDict('ColorFromColumn', {
    'color_rule': Literal["color_from_column"],
    'val_column': str
})

ColorMappingConfig = Union[
    ColorMapRules,
    ColorWhenNotNullRules,
    ColorFromColumn,
    ColorCategoricalRules
]

# Tooltip types
SimpleTooltip = TypedDict('SimpleTooltip', {
    'tooltip_type': Literal["simple"],
    'val_column': str
})

SummarySeriesTooltip = TypedDict('SummarySeriesTooltip', {
    'tooltip_type': Literal["summary_series"]
})

TooltipConfig = Union[SimpleTooltip, SummarySeriesTooltip]

# Column config types
BaseColumnConfig = TypedDict('BaseColumnConfig', {
    'displayer_args': DisplayerArgs,
    'color_map_config': NotRequired[ColorMappingConfig],
    'tooltip_config': NotRequired[TooltipConfig],
    'ag_grid_specs': NotRequired[Dict[str, Any]]  # AGGrid_ColDef
})

NormalColumnConfig = TypedDict('NormalColumnConfig', {
    'col_name': str,
    'header_name': str, #field
    'displayer_args': DisplayerArgs,
    'color_map_config': NotRequired[ColorMappingConfig],
    'tooltip_config': NotRequired[TooltipConfig],
    'ag_grid_specs': NotRequired[Dict[str, Any]]  # AGGrid_ColDef
})

MultiIndexColumnConfig = TypedDict('MultiIndexColumnConfig', {
    'col_path': List[str],
    'field': str,
    'displayer_args': DisplayerArgs,
    'color_map_config': NotRequired[ColorMappingConfig],
    'tooltip_config': NotRequired[TooltipConfig],
    'ag_grid_specs': NotRequired[Dict[str, Any]]  # AGGrid_ColDef
})
ColumnConfig = Union[NormalColumnConfig, MultiIndexColumnConfig]


PinnedRowConfig = TypedDict('PinnedRowConfig', {
    'primary_key_val': str,
    'displayer_args': DisplayerArgs,
    'default_renderer_columns': NotRequired[List[str]]  # used to render index column values with string not the specified displayer
})

ComponentConfig = TypedDict('ComponentConfig', {
    'height_fraction': NotRequired[float],
    'dfvHeight': NotRequired[int],  # temporary debugging prop
    'layoutType': NotRequired[Literal["autoHeight", "normal"]],
    'shortMode': NotRequired[bool],
    'selectionBackground': NotRequired[str],
    'className': NotRequired[str]
})

DFViewerConfig = TypedDict('DFViewerConfig', {
    'pinned_rows': List[PinnedRowConfig],
    'column_config': List[ColumnConfig],
    'left_col_configs': List[ColumnConfig],  # basically for the pandas index
    'extra_grid_config': NotRequired[Dict[str, Any]],  # GridOptions
    'component_config': NotRequired[ComponentConfig]
})

DisplayArgs = TypedDict('DisplayArgs', {
    'data_key':str,
    'df_viewer_config':DFViewerConfig,
    'summary_stats_key': str})

INDEX_COL_CONFIG:ColumnConfig = {'col_name': 'index', 'header_name':'index',
                       'displayer_args': {'displayer': 'obj'}}
EMPTY_DFVIEWER_CONFIG: DFViewerConfig = {
    'pinned_rows': [],
    'column_config': [],
    'left_col_configs': [INDEX_COL_CONFIG]
}


EMPTY_DF_DISPLAY_ARG: DisplayArgs = {
  'data_key': 'empty', 'df_viewer_config': EMPTY_DFVIEWER_CONFIG,
  'summary_stats_key': 'empty'}


SENTINEL_DF_1 = pd.DataFrame({'foo'  :[10, 20], 'bar' : ["asdf", "iii"]})
SENTINEL_DF_2 = pd.DataFrame({'col1' :[55, 55], 'col2': ["pppp", "333"]})


def merge_sds(*sds):
    """merge sds with later args taking precedence

    sub-merging of "overide_config"??
    """
    base_sd = {}
    for sd in sds:
        for column in sd.keys():
            base_sd[column] = merge_column(base_sd.get(column, {}), sd[column])
    return base_sd


def merge_column(base, new):
    """
    merge individual column dictionaries, with special handling for column_config_override
    """
    ret = base.copy()
    ret.update(new)

    base_override = base.get('column_config_override', {}).copy()
    new_override = new.get('column_config_override', {}).copy()
    base_override.update(new_override)

    if len(base_override) > 0:
        ret['column_config_override'] = base_override
    return ret


OverrideColumnConfig:TypeAlias = Dict[ColIdentifier, BaseColumnConfig]

def merge_column_config(styled_column_config:List[ColumnConfig],
                        df:pd.DataFrame,
    overide_column_configs:OverrideColumnConfig) -> List[ColumnConfig]:

    """
      merge_rule works on orignal column names

      merge_rule_rewritten works on rewritten_column names, it will be rarely used
      """
    existing_column_config: List[ColumnConfig] = styled_column_config.copy()
    ret_column_config: List[ColumnConfig] = []

    rewrites= dict( old_col_new_col(df))
    
    for row in existing_column_config:
        orig_col: ColIdentifier = row.get('header_name', None) or row.get('col_path', None)

        if orig_col in overide_column_configs:
            row.update(rewrite_override_col_references(rewrites, overide_column_configs[orig_col]))
        if row.get('merge_rule', 'blank') == 'hidden':

            continue
        ret_column_config.append(row)
    return ret_column_config

PartialColConfig:TypeAlias = Dict[str, Union[str, Dict[str, str]]]
def rewrite_override_col_references(rewrites: Dict[ColIdentifier, ColIdentifier], override:PartialColConfig) -> PartialColConfig:
    obj = copy.deepcopy(override)
    if obj.get('color_map_config'):
        if obj['color_map_config'].get('val_column'):
            val_col = obj['color_map_config']['val_column']
            # Only rewrite if the column exists in rewrites, otherwise keep original
            obj['color_map_config']['val_column'] = rewrites.get(val_col, val_col)

        if obj['color_map_config'].get('exist_column'):
            exist_col = obj['color_map_config']['exist_column']
            obj['color_map_config']['exist_column'] = rewrites.get(exist_col, exist_col)
    if obj.get('tooltip_config'):
        if obj['tooltip_config'].get('val_column'):
            val_col = obj['tooltip_config']['val_column']
            obj['tooltip_config']['val_column'] = rewrites.get(val_col, val_col)
    return obj


def merge_sd_overrides(final_sd:SDType, df:pd.DataFrame, overrides:SDType) -> SDType:
    """
      this is psecifically built for places where keys from the original dataframe will be used in 'overrides'
      those should be mapped onto the rewritten col_name
      """
    for old_col, new_col in old_col_new_col(df):
        if old_col in overrides:
            if new_col not in final_sd:
                final_sd[new_col] = {}
            final_sd[new_col].update(overrides[old_col])
    return final_sd

def safedel(dct:Dict[str, Any], key:str) -> Dict[str, Any]:
    if key in dct:
        del dct[key]
    return dct

    


#Union[pd.Index[Any], pd.MultiIndex]
def get_index_level_names(index:Any) -> List[str]:
    if isinstance(index, pd.MultiIndex):
        if all(x is None for x in index.names):
            index_level_names = ['' for idx_name in index.names]
        else:
            index_level_names = [str(idx_name) for idx_name in index.names]
    elif index.name is not None:
        index_level_names = [index.name]
    else:
        index_level_names = []
    return index_level_names

#Union[pd.Index[Any], pd.MultiIndex]
def get_empty_index_level_arr(index:Any) -> List[str]:
    if isinstance(index, pd.MultiIndex):
        index_level_names = ['' for idx_name in index.names]
    elif index.name is not None:
        index_level_names = [index.name]
    else:
        index_level_names = []
    return index_level_names

def index_names_empty(index:Any) -> bool:
    if isinstance(index, pd.MultiIndex):
        return all(x is None for x in index.names)
    return index.name is None
    

class StylingAnalysis(ColAnalysis):
    @classmethod
    def get_left_col_configs(cls, df:pd.DataFrame) -> List[ColumnConfig]:
        if not isinstance(df, pd.DataFrame):
            return [{'col_name': 'index', 'header_name':'index', 'displayer_args': {'displayer': 'obj'},
                     #'ag_grid_specs': {'pinned':'left'}

                     }]
        if index_names_empty(df.index) and index_names_empty(df.columns) and not isinstance(df.index, pd.MultiIndex):
            return [{'col_name': 'index', 'header_name':'index',
                             'displayer_args': {'displayer': 'obj'}}
                     ]
        base_col_path = get_empty_index_level_arr(df.columns)
        col_levels = get_index_level_names(df.columns)

        if not(isinstance(df.index, pd.MultiIndex)):
            if index_names_empty(df.index):
                col_levels.append('index')
            else:
                col_levels.append(df.index.name)
            return [{'col_path':col_levels, 'field':'index',
                     'displayer_args': {'displayer': 'obj'}}]
        ccs:List[ColumnConfig] = []

        for i, idx_name in enumerate(df.index.names):
            if idx_name is None and index_names_empty(df.columns):
                # if len(base_col_path) == 0:
                #     base_col_path = ['']
                ccs.append({'header_name':'', 'col_name':'index_' + to_chars(i),
                     'displayer_args': {'displayer': 'obj'}})
            else:
                if index_names_empty(df.index):
                    local_col_path = base_col_path.copy()
                else:
                    local_col_path = base_col_path.copy()
                    local_col_path.append(str(idx_name))
                ccs.append({'col_path': local_col_path, 'field':'index_' + to_chars(i),
                     'displayer_args': {'displayer': 'obj'}})
        if not index_names_empty(df.columns):
            for i, cl in enumerate(col_levels):
                ccs[-1]['col_path'][i] = cl
        # ccs[-1]['ag_grid_specs'] = {
	# 	    'headerClass': ['last-index-header-class'],
	# 	    'cellClass': ['last-index-cell-class'],
	# 	  }
                    

        return ccs

    provides_defaults: ColMeta = {}
    pinned_rows:  List[PinnedRowConfig] = []
    extra_grid_config: NotRequired[Dict[str, Any]] = {}
    component_config: NotRequired[ComponentConfig] = {}
    
    @classmethod
    def style_column(cls, col:str, _column_metadata: ColMeta) -> BaseColumnConfig:
        """
          This is the method that should be overridden. by subclasses
        """
        return {'displayer_args': {'displayer': 'obj'}}

    parquet_style_index: bool = True

    @classmethod
    def get_index_name(cls, df:pd.DataFrame) -> str :
        if cls.parquet_style_index:
            #"('index', '')"
            if isinstance(df.columns, pd.MultiIndex):
                extra_len = df.columns.nlevels - 1
                new_index = ['index'] + [''] * extra_len
                return str(tuple(new_index))
        return 'index'

    
    @classmethod
    def fix_column_config(cls, col: ColIdentifier, orig_col_name: ColIdentifier, base_cc:BaseColumnConfig) -> ColumnConfig:
        safedel(base_cc, 'col_name')
        safedel(base_cc, 'col_path')
        safedel(base_cc, 'field')
        safedel(base_cc, 'header_name')

        if isinstance(orig_col_name, tuple):
            base_cc['col_path'] = orig_col_name
            base_cc['field'] = str(col)  # sometimes numbers still creep in here
        else:
            base_cc['col_name'] = col
            base_cc['header_name'] = str(orig_col_name)  # sometimes numbers still creep in here
        return base_cc
    
    #what is the key for this in the df_display_args_dictionary
    df_display_name: str = "main"
    data_key: str = "main"
    summary_stats_key: str = 'all_stats'

    @classmethod
    def default_styling(cls, col_name:Union[Iterable[str], str], /) -> ColumnConfig:
        return cls.fix_column_config(col_name, col_name, {'displayer_args': {'displayer': 'obj'}})

    @classmethod
    def get_dfviewer_config(cls, sd:SDType, df:pd.DataFrame) -> DFViewerConfig:
        #index_config : ColumnConfig = cls.default_styling('index')
        return {
            'pinned_rows': cls.pinned_rows,
            'column_config': cls.style_columns(sd, df),
            'left_col_configs':  cls.get_left_col_configs(df),
            'extra_grid_config': cls.extra_grid_config,
            'component_config': cls.component_config
        }
                    
    @classmethod
    def style_columns(cls, sd:SDType, df:pd.DataFrame) -> List[ColumnConfig]:
        ret_col_config: List[ColumnConfig] = []
        skip_orig_cols = []
        for col, col_meta in sd.items():
            #FIXME: why does this come up here too
            if col_meta.get('merge_rule', None) == 'hidden':
                skip_orig_cols.append(col)

        rewrites= dict( old_col_new_col(df))
        for col, col_meta in sd.items():
            try:
                orig_col_name = col_meta.get('orig_col_name')
                if orig_col_name in skip_orig_cols or col_meta.get('merge_rule', None) == 'hidden':

                    continue
                #it actually gets tuples here
                base_style: ColumnConfig = cls.fix_column_config(col, orig_col_name,  cls.style_column(col, col_meta))
            except Exception as exc:
                if len(col_meta) == 0 and len(cls.requires_summary) > 0:
                    # this is called in instantiation without col_meta, and that can cause failures
                    # we want to just swallow these errors and not warn
                    pass
                else:
                    # something unexpected happened here, warn so that the develoepr is notified
                    logger.warning(f"Warning, styling failed from {cls} on column {col} with col_meta {col_meta} using default_styling instead")
                    logger.warning(exc)
                # Always provide a style, not providing a style
                # results in no display which is a very bad user
                # experience
                base_style = cls.default_styling(col)



            if 'column_config_override' in col_meta:
                #column_config_override, sent by the instantiation, gets set later
                cco: ColumnConfig = col_meta['column_config_override'] # pyright: ignore[reportAssignmentType]
                base_style.update(rewrite_override_col_references(rewrites, cco)) # pyright: ignore[reportCallIssue, reportArgumentType]

            if base_style.get('merge_rule') == 'hidden':
                continue
            ret_col_config.append(base_style)
        return ret_col_config
    

    
