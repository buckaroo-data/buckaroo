from typing import List, Union
from collections import defaultdict
import pandas as pd
import pandera.pandas as pa
from buckaroo.buckaroo_widget import BuckarooInfiniteWidget

from buckaroo.styling_helpers import obj_, pinned_histogram


def calculate_error_color_num(error_cross_df:pd.DataFrame) -> pd.DataFrame:
    orig_column_errortype_count = defaultdict(lambda : 0)
    tuple_col_num = {}
    for col, err_type in error_cross_df.columns:
        orig_column_errortype_count[col] += 1
        tuple_col_num[(col, err_type)] = orig_column_errortype_count[col] 

    new_data = {}
    for k in error_cross_df.columns:
        new_data[k] = error_cross_df[k].replace(1, tuple_col_num[k])

    unique_num_df = pd.DataFrame(new_data, columns=error_cross_df.columns)
    _error_num_data = {}

    first_level:str
    for first_level in unique_num_df.columns.get_level_values(0).unique():
        _error_num_data[first_level+"_color"] = unique_num_df.xs(first_level, axis=1, level=0).sum(axis=1)
    return pd.DataFrame(_error_num_data)  # this will be used to uniquely highlight error states


def get_column_reason_series(col_errors_df:pd.DataFrame) -> pd.Series[str]:
    """
    This function is about as far as possible from a vectorized operation.

    I couldn't figure it out.  Converting NA to '', means everything gets joined then you have to pull them out
    This would probably be cleaner as a tuple of non NA elements and a special displayer to make those work

    Open to suggestions
    """

    str_cust_error_data = {}
    for col in col_errors_df:
        base_ser = pd.Series([pd.NA] * len(col_errors_df), dtype='string', index=col_errors_df.index)
        base_ser.loc[col_errors_df[col]==1] = col
        str_cust_error_data[col] = base_ser
    str_err_df = pd.DataFrame(str_cust_error_data)

    ret_ser: List[str] = []
    for idx, row in str_err_df.iterrows():
        dna = row.dropna()
        if len(dna) > 0:
            ret_ser.append('|'.join(dna.tolist()))
        else:
            ret_ser.append(dna.values[0])
    return pd.Series(ret_ser, index=str_err_df.index, dtype='string')

def get_reason_df(cross_errors_df:pd.DataFrame) -> pd.DataFrame:
    reason_data = {}
    for first_level in cross_errors_df.columns.get_level_values(0).unique():
        col_df = cross_errors_df.xs(first_level, axis=1, level=0).dropna(how='all', axis=0)
        reason_data[first_level+"_reason"] = get_column_reason_series(col_df)
    return pd.DataFrame(reason_data)    


def get_fails(df:pd.DataFrame, schema:pa.DataFrameSchema) -> Union[None, pd.DataFrame]:
    """
      validate the dataframe with the schema.  Return any errors as a dataframe,
      if there are no errors return None

      I wish I had tests to show the actual example dataframes coming out of this function
      the index formatting is very important
      """
    try:
        schema.validate(df, lazy=True)
        return None
    except pa.errors.SchemaErrors as e:
        err_df: pd.DataFrame = e.failure_cases
        err_df['error_index'] = err_df['index']
        return err_df



eq_map: List[str] = ["transparent", "pink", "#73ae80", "#90b2b3", "#6c83b5", "brown"]
def make_col_config_overrides(df:pd.DataFrame): # -> OverrideColumnConfig
    """
      This generates col_config_overrides given an orginal dataframe

      This sets up the colormap config for each original column, linked to a _color column and _reason column
      it also hides the _color and _reason columns



    BaseColumnConfig = TypedDict('BaseColumnConfig', {
      'displayer_args': DisplayerArgs,
      'color_map_config': NotRequired[ColorMappingConfig],
      'tooltip_config': NotRequired[TooltipConfig],
      'ag_grid_specs': NotRequired[Dict[str, Any]]})  # AGGrid_ColDef

    OverrideColumnConfig:TypeAlias = Dict[str, BaseColumnConfig]

      """
    column_config_overrides = {}
    column:str
    for column in df.columns:
        column_config_overrides[column] = {
            'tooltip_config': { 'tooltip_type':'simple', 'val_column': column+'_reason'},
            'color_map_config': {
                'color_rule': 'color_categorical',
                'map_name': eq_map,
                'val_column': column + "_color"}}
        column_config_overrides[column +"_reason"] = {'merge_rule': 'hidden'}
        column_config_overrides[column +"_color"] = {'merge_rule': 'hidden'}
    return column_config_overrides

    
def BuckarooPandera(df:pd.DataFrame, schema:pa.DataFrameSchema):
    error_df = get_fails(df, schema)
    if error_df is None:
        print("all checks pass")
        return BuckarooInfiniteWidget(df)
    #these crosstab calls are necessary to pull the pandera results out into a useable format
    cross_df1 = pd.crosstab(error_df['error_index'], [error_df['column'], error_df['check']])
    cross_df1 = cross_df1.astype('Int64').replace(0, pd.NA).dropna(axis=1, how='all')
    color_df = calculate_error_color_num(cross_df1)
    reason_df = get_reason_df(cross_df1)
    #join the color columns with the reason columns and the original df
    complete_df = df.join(color_df, how='outer').join(reason_df, how='outer')
    cco = make_col_config_overrides(df)

    # it's important that 'index' is the first key in init_sd, othewise display is messed up. 
    # this is a bug in buckaroo
    init_sd = {'index':{}} 

    #pandera does something special with checks that aren't related to a particular cell
    column_errors = error_df[error_df['check_number'].isna()]
    full_df_checks = pd.crosstab(column_errors['check'], [column_errors['column']]).to_dict()
    init_sd.update(full_df_checks)
    base_pinned_rows = [
        obj_('dtype'), #{'primary_key_val': 'dtype',           'displayer_args': {'displayer': 'obj'}},
        pinned_histogram()]
    if len(full_df_checks) > 0:
        first_col = list(full_df_checks.keys())[0]
        for prop_name in full_df_checks[first_col].keys():
            base_pinned_rows.append(obj_(prop_name))
    bw = BuckarooInfiniteWidget(
        complete_df, column_config_overrides=cco,
        init_sd = init_sd,
        pinned_rows = base_pinned_rows)

    return bw
