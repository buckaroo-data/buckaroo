import marimo

__generated_with = "0.13.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import pandas as pd
    import pandera.pandas as pa
    from pandera import Column, Check
    from buckaroo.buckaroo_widget import BuckarooInfiniteWidget
    from collections import defaultdict
    return BuckarooInfiniteWidget, Check, Column, defaultdict, pa, pd


@app.cell
def _(pd):
    fruits = pd.DataFrame(
        {
            "name": ["apple", "banana", "apple", "orange"],
            "store": ["Aldi", "Walmart", "Walmart", "Aldi"],
            "price": [2, 1, 3, 4],
        }
    )

    fruits
    return (fruits,)


@app.cell
def _(BuckarooPandera, Check, Column, fruits, pa):
    available_fruits = ["apple", "banana", "orange"]
    nearby_stores = ["Aldi", "Walmart"]

    schema = pa.DataFrameSchema(    {
            "name": Column(str, Check.isin(available_fruits)),
            "store": Column(str, Check.isin(nearby_stores)),
            "price": Column(int, Check.less_than(4)),
        }
    )
    #val_result = schema.validate(fruits)
    #schema.
    BuckarooPandera(fruits, schema)
    return (schema,)


@app.cell
def _(BuckarooPandera, pd, schema):
    fruits2 = pd.DataFrame(
        {
            "name": ["apple", "banana", "apple", "orange"],
            "store": ["Aldi", "Walmart", "Walmart", "Aldi"],
            "price": [2, 1, 3, 2],
        }
    )
    BuckarooPandera(fruits2, schema)
    return (fruits2,)


@app.cell
def _(fruits2, get_fails, schema):
    error_df2 = get_fails(fruits2, schema)
    #column_errors = error_df2[error_df2['check_number'].isna()]
    #full_df_checks = pd.crosstab(column_errors['check'], [column_errors['column']]).to_dict()
    error_df2.to_dict()
    return


@app.cell
def _(Check, Column, pa, pd):
    def is_even(val):
        return val %2 == 1
    schema2 = pa.DataFrameSchema(
        {
            "customer_id": Column(
                dtype="int64",  # Use int64 for consistency
                checks=[
                    Check(lambda x: x > 0, element_wise=True), # IDs must be positive
                    Check(is_even, element_wise=True),
                    Check.isin(range(-50, 1000)), 
                    Check.isin(range(0, 1000))
                ],  # IDs between 1 and 999
                nullable=False),
            "name": Column(
                dtype="string",
                checks=[
                    Check.str_length(min_value=1),  # Names cannot be empty
                    Check(lambda x: x.strip() != "", element_wise=True)],
                nullable=False),
            "age": Column(
                dtype="int64",
                checks=[
                    Check.greater_than(0),  # Age must be positive
                    Check.less_than_or_equal_to(120),
                ],  # Age must be reasonable
                nullable=False),
            "email": Column(
                dtype="string",
                checks=[
                    Check.str_matches(
                        r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")],
                nullable=False,
            )})
    kd_df = pd.DataFrame(
        {
            #"customer_id": [None, -20, 3, 4, "invalid", 2000],  # "invalid" is not an integer
            "customer_id": pd.Series([pd.NA, -20, 3, 4, -5, 2000, 2001, 9], dtype='Int64'),  # "invalid" is not an integer
            "name": ["Maryam", "Jane", "", "Alice", "Bobby", "k", "v", "normal"],  # Empty name
            "age": [25, -5, 30, 45, 35, 150, 7, 25],  # Negative age is invalid
            "email": [
                "mrym@gmail.com",
                "jane.s@yahoo.com",
                "invalid_email",
                "alice@google.com",
                None,
                "asdasdf",
                None,
                'good@email.com'
            ]})
    return kd_df, schema2


@app.cell
def _(kd_df):
    kd_df
    return


@app.cell
def _(get_fails, kd_df, schema2):
    kd_error_df = get_fails(kd_df, schema2)
    kd_error_df
    return (kd_error_df,)


@app.cell
def _(kd_error_df, pd):
    cross_df1 = pd.crosstab(kd_error_df['error_index'], [kd_error_df['column'], kd_error_df['check']])
    cross_df1 = cross_df1.astype('Int64').replace(0, pd.NA).dropna(axis=1, how='all')
    #cross_df1.columns = cross_df1.columns.get_level_values(1)
    cross_df1
    return (cross_df1,)


@app.cell
def _(calculate_error_color_num, cross_df1):
    calculate_error_color_num(cross_df1)
    return


@app.cell
def _(defaultdict, pd):
    def calculate_error_color_num(error_cross_df):

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

        for first_level in unique_num_df.columns.get_level_values(0).unique():
            _error_num_data[first_level+"_color"] = unique_num_df.xs(first_level, axis=1, level=0).sum(axis=1)
        return pd.DataFrame(_error_num_data)  # this will be used to uniquely highlight error states
    return (calculate_error_color_num,)


@app.cell
def _(cross_df1, pd):
    def get_column_reason_series(col_errors_df):
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

        ret_ser = []
        for idx, row in str_err_df.iterrows():
            dna = row.dropna()
            if len(dna) > 0:
                ret_ser.append('|'.join(dna.tolist()))
            else:
                ret_ser.append(dna.values[0])
        return pd.Series(ret_ser, index=str_err_df.index, dtype='string')
    get_column_reason_series(cross_df1.xs('customer_id', axis=1, level=0).dropna(how='all', axis=0))
    return (get_column_reason_series,)


@app.cell
def _(cross_df1, get_column_reason_series):
    get_column_reason_series(cross_df1.xs('age', axis=1, level=0).dropna(how='all', axis=0))
    return


@app.cell
def _(cross_df1, get_column_reason_series, pd):
    def get_reason_df(cross_errors_df):
        reason_data = {}
        for first_level in cross_errors_df.columns.get_level_values(0).unique():
            col_df = cross_errors_df.xs(first_level, axis=1, level=0).dropna(how='all', axis=0)
            reason_data[first_level+"_reason"] = get_column_reason_series(col_df)
        return pd.DataFrame(reason_data)    
    get_reason_df(cross_df1)
    return (get_reason_df,)


@app.cell
def _(calculate_error_color_num, cross_df1, get_reason_df, kd_df):
    _color_df = calculate_error_color_num(cross_df1)
    _reason_df = get_reason_df(cross_df1)
    kd_df.join(_color_df, how='outer').join(_reason_df, how='outer')
    return


@app.cell
def _():
    return


@app.cell
def _(
    BuckarooInfiniteWidget,
    calculate_error_color_num,
    get_fails,
    get_reason_df,
    make_col_config_overrides,
    pd,
):
    from buckaroo.styling_helpers import obj_, float_, pinned_histogram
    def BuckarooPandera(df, schema):
        error_df = get_fails(df, schema)
        if error_df is None:
            print("all checks pass")
            return BuckarooInfiniteWidget(df)
        cross_df1 = pd.crosstab(error_df['error_index'], [error_df['column'], error_df['check']])
        cross_df1 = cross_df1.astype('Int64').replace(0, pd.NA).dropna(axis=1, how='all')
        color_df = calculate_error_color_num(cross_df1)
        reason_df = get_reason_df(cross_df1)
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

    return (BuckarooPandera,)


@app.cell
def _(BuckarooPandera, kd_df, schema2):
    BuckarooPandera(kd_df, schema2)
    return


@app.cell
def _():
    eq_map = ["transparent", "pink", "#73ae80", "#90b2b3", "#6c83b5", "brown"];
    def make_col_config_overrides(df):
        column_config_overrides = {}
        for column in df:
            column_config_overrides[column] = {
                'tooltip_config': { 'tooltip_type':'simple', 'val_column': column+'_reason'},
                'color_map_config': {
                    'color_rule': 'color_categorical',
                    'map_name': eq_map,
                    'val_column': column + "_color"}}
            column_config_overrides[column +"_reason"] = {'merge_rule': 'hidden'}
            column_config_overrides[column +"_color"] = {'merge_rule': 'hidden'}
        return column_config_overrides
    return (make_col_config_overrides,)


@app.cell
def _(pa):
    def get_fails(df, schema):
        try:
            validated_df = schema.validate(df, lazy=True)
            return None
        except pa.errors.SchemaErrors as e:
            err_df = e.failure_cases
            err_df['error_index'] = err_df['index']
            return err_df
    return (get_fails,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
