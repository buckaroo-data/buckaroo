import marimo

__generated_with = "0.12.8"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        # Buckaroo Styling Gallery
        Buckaroo can be extensively styled.  This gallery shows many examples of the column configuration language.
        In this case all of the configs are passed in via `column_config_overrides`. 
        Each call looks approximately like
        ```python
        BuckarooInfiniteWidget(df, column_config_overrides={
            "float_obj_displayer": {
                "displayer_args": {
                    "displayer": "obj"}}})
        ```

        It is also possible to write your own styling functions that look at summary stats and return configs for columns.  This is detailed in [Styling Howto](https://github.com/paddymul/buckaroo/blob/main/docs/example-notebooks/Styling-Howto.ipynb)
        """
    )
    return


@app.cell
def _(DFViewerInfinite, dropdown_dict, format_json, mo):
    mo.vstack(
        [
            dropdown_dict,
            mo.hstack([
                mo.md(dropdown_dict.value[2]),
                mo.ui.text_area(format_json(dropdown_dict.value[1]), disabled=True, max_length=500, rows=15, full_width=True)],
                     widths="equal"
                     ),
            DFViewerInfinite(dropdown_dict.value[0], column_config_overrides = dropdown_dict.value[1])
        ]
    )
    return


@app.cell(hide_code=True)
def _(DataFrame):
    _ts_col = ["2020-01-01 01:00Z", "2020-01-01 02:00Z", "2020-02-28 02:00Z", "2020-03-15 02:00Z", None]
    _datetime_df = DataFrame(
        {'timestamp': _ts_col,
         'timestamp_obj_displayer': _ts_col,
         'timestamp_datetime_default_displayer':_ts_col,
         'timestamp_datetime_locale_en-US':_ts_col,
         'timestamp_datetime_locale_en-US-Long':_ts_col,
         'timestamp_datetime_locale_en-GB':_ts_col})

    def _locale_col_conf(locale, args={}):
        return {'displayer_args': {'displayer': 'datetimeLocaleString',
                                'locale':locale,
                                'args':args}}
    _datetime_config = {
        'timestamp_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},    
        'timestamp_datetime_default_displayer' : {'displayer_args':  {'displayer': 'datetimeDefault'}},
        'timestamp_datetime_locale_en-US' : _locale_col_conf('en-US'),
        'timestamp_datetime_locale_en-US-Long': _locale_col_conf('en-US', { 'weekday': 'long'}),
        'timestamp_datetime_locale_en-GB' : _locale_col_conf('en-GB')}
    _datetime_md = """
    # Datetime displayers

    These are used to control the display of datetime columns

    ```typescript
    interface DatetimeDefaultDisplayerA {
        displayer: 'datetimeDefault';}
    interface DatetimeLocaleDisplayerA {
        displayer: 'datetimeLocaleString';
        locale: 'en-US' | 'en-GB' | 'en-CA' | 'fr-FR' | 'es-ES' | 'de-DE' | 'ja-JP';
      args: Intl.DateTimeFormatOptions;}
    ```

    Mozilla has additonal [docs for Intl DatetimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat)
    """
    datetime_config = (_datetime_df, _datetime_config, _datetime_md)
    return (datetime_config,)


@app.cell(hide_code=True)
def _(DataFrame):
    _base_str_col = ["asdf", "qwerty", "really long string, much  much longer",
                    None,  "A"]

    _str_df = DataFrame({
        'strings_string_displayer_max_len': _base_str_col,
        'strings_obj_displayer':  _base_str_col,
        'strings_string_displayer': _base_str_col})
    _str_config =  {
        'strings_string_displayer_max_len': {'displayer_args': {'displayer': 'string', 'max_length':35}},
        'strings_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},      
        'strings_string_displayer': {'displayer_args': {'displayer': 'string'}},
    }
    _str_md = """
    ## String Displayer
    The string displayer allows you to set a max_length parameter
    ```typescript
    interface StringDisplayerA {
        displayer: 'string';
        max_length?: number;}
    ```
    """
    str_config = (_str_df, _str_config, _str_md)
    return (str_config,)


@app.cell(hide_code=True)
def _(DataFrame):
    _float_col = [5, -8, 13.23, -8.01, -999.345245234, None]
    _float_df = DataFrame({
        'float_obj_displayer': _float_col,
        'float_float_displayer_1__3': _float_col,
        'float_float_displayer_0__3': _float_col,
        'float_float_displayer_3__3': _float_col,
        'float_float_displayer_3_13': _float_col})
    def _float_col_conf(min_digits, max_digits):
        return {'displayer_args':
                { 'displayer': 'float', 'min_fraction_digits':min_digits, 'max_fraction_digits': max_digits}}
    _float_config = {
        'float_obj_displayer':  {'displayer_args': {'displayer': 'obj'}},      
        'float_float_displayer_1__3' : _float_col_conf(1,3),
        'float_float_displayer_0__3' : _float_col_conf(0,3),
        'float_float_displayer_3__3' : _float_col_conf(3,3),
        'float_float_displayer_3_13' : _float_col_conf(3,13)}
    _float_md = """
    ## Float displayers
    the `float` displayer allows you to control the number of digits displayed after the decimal point.

    ```typescript
    interface FloatDisplayerA {
        displayer: 'float';
        min_fraction_digits: number;
        max_fraction_digits: number;}
    ```

    """
    float_config = (_float_df, _float_config, _float_md)
    return (float_config,)


@app.cell(hide_code=True)
def _(pd):
    _link_df = pd.DataFrame({'raw':
                             ['https://github.com/paddymul/buckaroo', 'https://github.com/pola-rs/polars'],
                             'linkify' :
                             ['https://github.com/paddymul/buckaroo', 'https://github.com/pola-rs/polars']})
    _link_config = {'linkify': {'displayer_args':  {  'displayer': 'linkify'}}}
    _link_md = """
    ## Link Displayer
    The link displayer is a special displayer that converts text into a link

    ```typescript
    interface LinkifyDisplayerA {
        displayer: "linkify";
    }
    ```
    """
    link_config = (_link_df, _link_config, _link_md)
    return (link_config,)


@app.cell(hide_code=True)
def _(pd):
    # I pulled this out into a separate variable so we can eventually
    # display it in a spearate code block
    _histogram_data = ['histogram', 
          [{'name': 'NA', 'NA': 100.0}],
          [{'name': 1, 'cat_pop': 44.0}, {'name': 'NA', 'NA': 56.0}],
          [{'name': 'long_97', 'cat_pop': 0.0},
           {'name': 'long_139', 'cat_pop': 0.0},
           {'name': 'long_12', 'cat_pop': 0.0},
           {'name': 'long_134', 'cat_pop': 0.0},
           {'name': 'long_21', 'cat_pop': 0.0},
           {'name': 'long_44', 'cat_pop': 0.0},
           {'name': 'long_58', 'cat_pop': 0.0},
           {'name': 'longtail', 'longtail': 77.0},
           {'name': 'NA', 'NA': 20.0}],
          [{'name': 'long_113', 'cat_pop': 0.0},
           {'name': 'long_116', 'cat_pop': 0.0},
           {'name': 'long_33', 'cat_pop': 0.0},
           {'name': 'long_72', 'cat_pop': 0.0},
           {'name': 'long_122', 'cat_pop': 0.0},
           {'name': 'long_6', 'cat_pop': 0.0},
           {'name': 'long_83', 'cat_pop': 0.0},
           {'name': 'longtail', 'unique': 50.0, 'longtail': 47.0}]]
    _histogram_df = pd.DataFrame({
        'names': ['index', 'all_NA', 'half_NA', 'longtail', 'longtail_unique'],
        'histogram_props': _histogram_data})

    _histogram_config = {
        'histogram_props': {'displayer_args': {'displayer': 'histogram'}}}
    _histogram_md = """
    ## Histogram Displayer

        Histograms are normally shown in summary stats and pinned_rows, they can also be displayed in the main table.

    ```typescript
    interface HistogramDisplayerA {
        displayer: "histogram";
    }
    ```
    This table is displayed with the following data
    ```python
             [[{'name': 'NA', 'NA': 100.0}],
              [{'name': 1, 'cat_pop': 44.0}, {'name': 'NA', 'NA': 56.0}],
              [{'name': 'long_97', 'cat_pop': 0.0},
               {'name': 'long_139', 'cat_pop': 0.0},
               {'name': 'long_12', 'cat_pop': 0.0},
               {'name': 'long_134', 'cat_pop': 0.0},
               {'name': 'long_21', 'cat_pop': 0.0},
               {'name': 'long_44', 'cat_pop': 0.0},
               {'name': 'long_58', 'cat_pop': 0.0},
               {'name': 'longtail', 'longtail': 77.0},
               {'name': 'NA', 'NA': 20.0}],
              [{'name': 'long_113', 'cat_pop': 0.0},
               {'name': 'long_116', 'cat_pop': 0.0},
               {'name': 'long_33', 'cat_pop': 0.0},
               {'name': 'long_72', 'cat_pop': 0.0},
               {'name': 'long_122', 'cat_pop': 0.0},
               {'name': 'long_6', 'cat_pop': 0.0},
               {'name': 'long_83', 'cat_pop': 0.0},
               {'name': 'longtail', 'unique': 50.0, 'longtail': 47.0}]]
    ```
    """

    histogram_config = (_histogram_df, _histogram_config, _histogram_md)
    return (histogram_config,)


@app.cell(hide_code=True)
def _(DataFrame):
    _png_smiley = 'iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAApgAAAKYB3X3/OAAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAANCSURBVEiJtZZPbBtFFMZ/M7ubXdtdb1xSFyeilBapySVU8h8OoFaooFSqiihIVIpQBKci6KEg9Q6H9kovIHoCIVQJJCKE1ENFjnAgcaSGC6rEnxBwA04Tx43t2FnvDAfjkNibxgHxnWb2e/u992bee7tCa00YFsffekFY+nUzFtjW0LrvjRXrCDIAaPLlW0nHL0SsZtVoaF98mLrx3pdhOqLtYPHChahZcYYO7KvPFxvRl5XPp1sN3adWiD1ZAqD6XYK1b/dvE5IWryTt2udLFedwc1+9kLp+vbbpoDh+6TklxBeAi9TL0taeWpdmZzQDry0AcO+jQ12RyohqqoYoo8RDwJrU+qXkjWtfi8Xxt58BdQuwQs9qC/afLwCw8tnQbqYAPsgxE1S6F3EAIXux2oQFKm0ihMsOF71dHYx+f3NND68ghCu1YIoePPQN1pGRABkJ6Bus96CutRZMydTl+TvuiRW1m3n0eDl0vRPcEysqdXn+jsQPsrHMquGeXEaY4Yk4wxWcY5V/9scqOMOVUFthatyTy8QyqwZ+kDURKoMWxNKr2EeqVKcTNOajqKoBgOE28U4tdQl5p5bwCw7BWquaZSzAPlwjlithJtp3pTImSqQRrb2Z8PHGigD4RZuNX6JYj6wj7O4TFLbCO/Mn/m8R+h6rYSUb3ekokRY6f/YukArN979jcW+V/S8g0eT/N3VN3kTqWbQ428m9/8k0P/1aIhF36PccEl6EhOcAUCrXKZXXWS3XKd2vc/TRBG9O5ELC17MmWubD2nKhUKZa26Ba2+D3P+4/MNCFwg59oWVeYhkzgN/JDR8deKBoD7Y+ljEjGZ0sosXVTvbc6RHirr2reNy1OXd6pJsQ+gqjk8VWFYmHrwBzW/n+uMPFiRwHB2I7ih8ciHFxIkd/3Omk5tCDV1t+2nNu5sxxpDFNx+huNhVT3/zMDz8usXC3ddaHBj1GHj/As08fwTS7Kt1HBTmyN29vdwAw+/wbwLVOJ3uAD1wi/dUH7Qei66PfyuRj4Ik9is+hglfbkbfR3cnZm7chlUWLdwmprtCohX4HUtlOcQjLYCu+fzGJH2QRKvP3UNz8bWk1qMxjGTOMThZ3kvgLI5AzFfo379UAAAAASUVORK5CYII='

    _img_df = DataFrame({'raw':    [_png_smiley, None],
                    'img_displayer' : [_png_smiley, None]})
    _img_config = {
        'raw':           {'displayer_args': {'displayer': 'string', 'max_length':40}},
        'img_displayer': {'displayer_args': {'displayer': 'Base64PNGImageDisplayer'},
                      'ag_grid_specs' : {'width':150}}}
    _img_md = """
    # Image displayer
    The image displayer is used to display an image from base64 data in a cell.

    ```typescript
    interface Base64PNGImageDisplayerA {
        displayer: "Base64PNGImageDisplayer";
    }
    ```
        """

    img_config = (_img_df, _img_config, _img_md)
    return (img_config,)


@app.cell(hide_code=True)
def _(pd):
    _error_df = pd.DataFrame({
        'a': [10, 20, 30],
        'err_messages': [None, "a must be less than 19, it is 20", "a must be less than 19, it is 30"]})

    _error_config = {
        'a': {'color_map_config': {
            'color_rule': 'color_not_null',
            'conditional_color': 'red',
            'exist_column': 'err_messages'}}}
    _error_md = """
    ## Color_map_config
    color_map_config is a spearate property from `displayer` and can be combined with displayer

    This example shows `color_not_null`.  A different background color is used when `exist_column` is not null.
    This is very useful for highlighting errors
    ```typescript
    interface ColorWhenNotNullRules {
        color_rule: "color_not_null";
        conditional_color: string | "red";
        exist_column: string;
    }
    ```

    """
    error_config = (_error_df, _error_config, _error_md)
    return (error_config,)


@app.cell(hide_code=True)
def _(DataFrame):
    _color_df = DataFrame({
        'a': [10, 20, 30],
        'a_colors': ['red', '#d3a', 'green']})

    _color_from_col_config={
        'a': { 'color_map_config': {
          'color_rule': 'color_from_column',
          'col_name': 'a_colors'}}}
    _color_from_col_md = """
    ## color_from_column
    `color_from_column` is used to explicitly set a background color in another column.  Any valid html color works
    ```typescript
    interface ColorFromColumn {
        color_rule: "color_from_column";
        val_column: string;
    }
    ```
    """
    color_from_col_config = (_color_df, _color_from_col_config, _color_from_col_md)
    return (color_from_col_config,)


@app.cell(hide_code=True)
def _(DataFrame, np):
    _ROWS = 200
    #the next dataframe is used for multiple examples
    typed_df = DataFrame(
        {'int_col':np.random.randint(1,50, _ROWS),
         'float_col': np.random.randint(1,30, _ROWS)/.7,
         "str_col": ["foobar"]* _ROWS})
    _tooltip_config = {
        'str_col':
            {'tooltip_config': { 'tooltip_type':'simple', 'val_column': 'int_col'}}}
    _tooltip_md = """
    ## Tooltip_config
    Tooltips are configured with the `tooltip_config` property (not a `displayer`)
    `val_column` is the column the tooltip should be pulled from.  Sometimes it is useful to have val_column be the current column if you want a narrower column but the full value also avaialable on hover.  
    ```typescript
    interface SimpleTooltip {
        tooltip_type: "simple";
        val_column: string;
    }
    ```
    NB: Currently broken because of JS/ag-grid problems so this isn't currently included.
    """
    tooltip_config = (typed_df, _tooltip_config, _tooltip_md)
    return tooltip_config, typed_df


@app.cell(hide_code=True)
def _(typed_df):
    _colormap_config = {
        'float_col': {'color_map_config': {
            'color_rule': 'color_map',
            'map_name': 'BLUE_TO_YELLOW',
            'val_column': 'int_col'
        }}}
    _colormap_md = """
    ## color_map_config
    `color_rule:"color_map"` selects a background based on a color_map, and where the cell value fits into that range.
    `val_column` can be used to color the column based on values in a different column


    ```typescript
    export type ColorMap = "BLUE_TO_YELLOW" | "DIVERGING_RED_WHITE_BLUE" | string[];
    interface ColorMapRules {
        color_rule: "color_map";
        map_name: ColorMap;
        //optional, the column to base the ranges on. the proper
        //histogram_bins must still be sent in for that column
        val_column?: string;
    }
    ```
    """
    colormap_config = (typed_df, _colormap_config, _colormap_md)
    return (colormap_config,)


@app.cell(hide_code=True)
def _(DataFrame):
    _explicit_colormap_df = DataFrame({
        "flag_column": [0, 1, 2, 3, 4, 5, 6, 7, 4, 3, 3, 2, 1, 0]
    })
    _colormap_config = {
        'flag_column': {'color_map_config': {
            'color_rule': 'color_map',
            'map_name': ["green", "blue", "red", "orange", "purple"]
        }}}
    _colormap_md = """
    ## color_map_config
    In this example we pass in an explicit color map. This is a bit tricky to use, there are some issues with the histogram ranges and how colors are selected. This is very useful for flagging a value from a discrete set of conditions.

    `color_rule:"color_map"` selects a background based on a color_map, and where the cell value fits into that range.
    `val_column` can be used to color the column based on values in a different column




    ```typescript
    export type ColorMap = "BLUE_TO_YELLOW" | "DIVERGING_RED_WHITE_BLUE" | string[];
    interface ColorMapRules {
        color_rule: "color_map";
        map_name: ColorMap;
        //optional, the column to base the ranges on. the proper
        //histogram_bins must still be sent in for that column
        val_column?: string;
    }
    ```
    """
    explicit_colormap_config = (_explicit_colormap_df, _colormap_config, _colormap_md)
    return (explicit_colormap_config,)


@app.cell
def _(
    colormap_config,
    error_config,
    explicit_colormap_config,
    float_config,
    histogram_config,
    img_config,
    link_config,
    mo,
    str_config,
):
    dfs = {"float_config": float_config, "str_config": str_config,
           "histogram_config": histogram_config, "img_config": img_config,
           "link_config": link_config,
           "colormap_config": colormap_config, "error_config": error_config, 
           "explicit_colormap_config": explicit_colormap_config
           # disabled because of js bug with tooltips
           #"tooltip_config":tooltip_config, 
           #"color_from_column": color_from_col_config

           }

    dropdown_dict = mo.ui.dropdown(
        options=dfs,
        value="colormap_config",
        label="Choose the config",
    )
    return dfs, dropdown_dict


@app.cell
async def _():
    import marimo as mo
    import pandas as pd
    import numpy as np
    import micropip
    await micropip.install("http://localhost:8000/public/buckaroo-0.9.15-py3-none-any.whl")
    import buckaroo
    from buckaroo import BuckarooInfiniteWidget
    from buckaroo.buckaroo_widget import DFViewerInfinite
    # Extra utility functions and marimo overrides
    from buckaroo.marimo_utils import marimo_monkeypatch, BuckarooDataFrame as DataFrame

    # this overrides pd.read_csv and pd.read_parquet to return BuckarooDataFrames which overrides displays as BuckarooWidget, not the default marimo table
    marimo_monkeypatch()
    import json
    import re
    def format_json(obj):
        """
          Formats obj to json  string to remove unnecessary whitespace.
          Returns:
              The formatted JSON string.
        """
        json_string = json.dumps(obj, indent=4)
        # Remove whitespace before closing curly braces
        formatted_string =   re.sub(r'\s+}', '}', json_string)
        #formatted_string = json_string
        return formatted_string
    return (
        BuckarooInfiniteWidget,
        DFViewerInfinite,
        DataFrame,
        buckaroo,
        format_json,
        json,
        marimo_monkeypatch,
        micropip,
        mo,
        np,
        pd,
        re,
    )


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
