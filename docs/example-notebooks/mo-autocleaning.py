import marimo

__generated_with = "0.17.6"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Autocleaning with Buckaroo

    Dealing with dirty data accounts for a large portion of the time in doing data work. We know what good data looks like, and we know the individual pandas commands to clean columns. But we have to type the same commands over and over again.

    Buckaroo separates data cleaning for users into four steps

    1. Look at the original data with your eyes
    2. Cycle through different cleaning approaches
    3. Approve which cleaned columns you like
    4. Optionally take the generated code and use it as a function

    Buckaroo performs these tasks interactively and quickly because it uses heuristics, not an LLM.

    All of this is customizeable.
    """)
    return


@app.cell
def _(MyAutocleaningBuckaroo, dirty_df):
    from buckaroo.buckaroo_widget import AutocleaningBuckaroo
    #MyAutocleaningBuckaroo(pd.concat([dirty_df]*3000)) # to see how this works on more rows
    mybw = MyAutocleaningBuckaroo(dirty_df)
    mybw
    return (mybw,)


@app.cell
def _(mybw):
    mybw.buckaroo_state
    return


@app.cell
def _(pd):
    def clean(df):
        TRUE_SYNONYMS = ['true', 'yes', 'on', '1']
        FALSE_SYNONYMS = ['false', 'no', 'off', '0']
        _ser = df['mostly_bool']
        _int_sanitize = _ser.replace(1, True).replace(0, False) 
        _real_bools = _int_sanitize.isin([True, False])
        _boolean_ser = _int_sanitize.where(_real_bools, pd.NA).astype('boolean')    
        _str_ser = _ser.astype('string').str.lower().str.strip()
        _trues = _str_ser.isin(TRUE_SYNONYMS).replace(False, pd.NA).astype('boolean')
        _falses =  ~ (_str_ser.isin(FALSE_SYNONYMS).replace(False, pd.NA)).astype('boolean')
        _combined = _boolean_ser.fillna(_trues).fillna(_falses)    

        df['mostly_bool'] = _combined
        return df
    #cdf = clean(dirty_df.copy())
    #cdf
    return


@app.cell
def _(pd):
    dirty_df = pd.DataFrame(
        {
            "untouched_a": [10, 20, 30, 40, 10, 20.3, None, 8, 9, 10, 11, 20, None],
            "mostly_ints": [
                "3",
                "4",
                "a",
                "5",
                "5",
                "b9",
                None,
                " 9",
                "9-",
                11,
                "867-5309",
                "-9",
                None,
            ],
            "us_dates": [
                "",
                "07/10/1982",
                "07/15/1982",
                "7/10/1982",
                "17/10/1982",
                "03/04/1982",
                "03/02/2002",
                "12/09/1968",
                "03/04/1982",
                "",
                "06/22/2024",
                "07/4/1776",
                "07/20/1969",
            ],
            "mostly_bool": [
                True,
                "True",
                "Yes",
                "On",
                "false",
                False,
                "1",
                "Off",
                "0",
                " 0",
                "No",
                1,
                None,
            ],
        }
    )
    return (dirty_df,)


@app.cell
def _(mo):
    mo.md(r"""
    # Writing your own cleaning routines
    Let's start by writing a function to clean a column.  Here we are going to strip all non digit and period characters then try to coerce to int
    """)
    return


@app.cell
def _(DataFrame, dirty_df, pd):
    import re
    def strip_int_and_period(orig_ser):
        if pd.api.types.is_object_dtype(orig_ser):
            ser = orig_ser.astype("string")
        elif not pd.api.types.is_string_dtype(orig_ser):
            #we can only work on string dtype
            return orig_ser
        else:
            #we have a string_dtype
            ser = orig_ser
        #we can only deal with string series
        digits_and_period = re.compile(r"[^\d\.]")
        #replace everything that's not a digit or a period with the empty stirng
        only_numeric_str_ser = ser.str.replace(digits_and_period, "", regex=True)
        numeric_ser = pd.to_numeric(only_numeric_str_ser, errors="coerce") #, dtype_backend="pyarrow")
        return numeric_ser.astype('Int64')
    DataFrame({'orig': dirty_df['mostly_ints'], 'cleaned': strip_int_and_period(dirty_df['mostly_ints'])})
    return re, strip_int_and_period


@app.cell
def _(mo):
    mo.md(r"""
    # Writing a fraction function
    We now have a cleaning function, we'll get back to integrating it into the Buckaroo UI in a little bit

    Fraction functions return the fraction of a column (0-1) that tells the fraction of values that are succesfully converted with this function.  Buckaroo uses fraction fuctions to integrate with heuristics to choose the correct cleaning function (if any) to apply to a column.

    This fraction function is fairly simple, based on the conversion function.
    """)
    return


@app.cell
def _(pd, strip_int_and_period):
    # I thought I could just call isna on the converted series, but for non string/object, that will give an improper result
    def strip_int_and_period_frac(ser):
        if not (pd.api.types.is_object_dtype(ser) or pd.api.types.is_string_dtype(ser)):
            return 0
        converted = strip_int_and_period(ser)
        non_na_count = (~(converted.isna())).sum()
        return non_na_count / len(ser)
    return (strip_int_and_period_frac,)


@app.cell
def _(dirty_df, strip_int_and_period_frac):
    #Try it out on dirty_df
    {'untouched_a':           strip_int_and_period_frac(dirty_df['untouched_a']),
     'mostly_ints':           strip_int_and_period_frac(dirty_df['mostly_ints']),
     'mostly_bool': strip_int_and_period_frac(dirty_df['mostly_bool'])}
    #so we can see that ['b'] is a good fit, the other two are not
    return


@app.cell
def _(mo):
    mo.md(r"""
    # Picking cleaning methods with heuristics

    We have multiple available cleaning methods for each column, and we need a way to choose which one to use. Enter heuristics, and heuristic lang. Heuristic lang is a mini lisp language that allows you to choose the best fit for a column.

    We also need to wrap our frac function into a ColAnalysis class.

    BaseHeuristic Genops generates commands for the lowcode UI based on which rule has the highest score.
    """)
    return


@app.cell
def _(pd, strip_int_and_period_frac):
    # we have defined other functions in the buckaroo code
    from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis

    from buckaroo.customizations.heuristics import BaseHeuristicCleaningGenOps
    from buckaroo.jlisp.lisp_utils import s
    from buckaroo.customizations.pd_fracs import (str_bool_frac, regular_int_parse_frac, us_dates_frac, cache_series_func)

    cached_strip_int_and_period_frac = cache_series_func(strip_int_and_period_frac)

    class HeuristicFracs(ColAnalysis):
        provides_defaults = dict(
            str_bool_frac=0,
            regular_int_parse_frac=0,
            strip_int_parse_frac=0,
            us_dates_frac=0,
        )

        @staticmethod
        def series_summary(sampled_ser, ser):
            if not (
                pd.api.types.is_string_dtype(ser)
                or pd.api.types.is_object_dtype(ser)
            ):
                return {} # the default 0 values will be returned

            return dict(
                str_bool_frac=str_bool_frac(ser),
                regular_int_parse_frac=regular_int_parse_frac(ser),
    #            strip_int_parse_frac=strip_int_and_period_frac(ser),
                strip_int_parse_frac=cached_strip_int_and_period_frac(ser),
                us_dates_frac=us_dates_frac(ser),
            )

    frac_name_to_command = {
        "str_bool_frac": "str_bool",
        "regular_int_parse_frac": "regular_int_parse",
        "strip_int_parse_frac": "strip_int_parse",
        "us_dates_frac": "us_date",
    }

    class ConvservativeCleaningGenops(BaseHeuristicCleaningGenOps):
        requires_summary = [
            "str_bool_frac",
            "regular_int_parse_frac",
            "strip_int_parse_frac",
            "us_dates_frac"]

        rules = {
            "str_bool_frac":          "(f> 0.75)",        # f> is a special operator that says "if this fraction is greater then"
            "regular_int_parse_frac": "(f> 0.85)",       # you can write scheme here
            "strip_int_parse_frac":   [s("f>"), 0.9],    # or JLisp
            "none":                   [s("none-rule")],  # none is important, we want to have a default rule
            "us_dates_frac": [s("primary"), [s("f>"), 0.8]]}  #primary is a special operator that gives this rule a boost if it matches

        rules_op_names = frac_name_to_command
    return ConvservativeCleaningGenops, HeuristicFracs, s


@app.cell
def _(mo):
    mo.md("""
    # Writing a low code UI command

    We now need to write a command for the lowcode UI that corresponds with the
    """)
    return


@app.cell
def _(Command, re, s, strip_int_and_period):
    class StripIntParse(Command):
        # These are the default arguments that the lowcode UI uses for this command
        command_default = [s("strip_int_parse"), s("df"), "col"] 
        # Unused here, but these are the argument types for the lowcode UI
        command_pattern = []

        @staticmethod
        def transform(df, col):
            _digits_and_period = re.compile(r"[^\d\.]")
            print("my strip_int_and_period")
            df[col] = strip_int_and_period(df[col])
            return df

        #transform to py is a function that returns equivalent python code. This is used for codegen
        @staticmethod
        def transform_to_py(df, col):
            return f"""    _digits_and_period = re.compile(r'[^\\d\\.]')
        _ser = df['{col}']
        _reg_parse = _ser.apply(pd.to_numeric, errors='coerce')
        _strip_parse = _ser.str.replace(_digits_and_period, "", regex=True).apply(pd.to_numeric, errors='coerce', dtype_backend='pyarrow')
        _combined = _reg_parse.fillna(_strip_parse)
        df['{col}'] = _combined"""
    return (StripIntParse,)


@app.cell
def _(mo):
    mo.md(r"""
    # Putting it all together with Autocleaning Config

    Autocleaning config combines a set of fracs, genereate ops, and commands into a named cleanign configuration
    This is a place you could play with a different implementation of a frac, heuristic, or command and give it a name in the UI.  For the most part I expect users to have different Heuristics.
    """)
    return


@app.cell
def _(ConvservativeCleaningGenops, HeuristicFracs, StripIntParse):
    from buckaroo.customizations.pandas_commands import (
        SafeInt,
        DropCol,
        FillNA,
        GroupBy,
        NoOp,
        Search,
    )
    from buckaroo.customizations.pandas_cleaning_commands import (
        IntParse,
        StrBool,
        USDate,
    )
    from buckaroo.dataflow.autocleaning import AutocleaningConfig
    # We import a bunch of other command classes
    class ConservativeAC(AutocleaningConfig):
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

        #quick command classes are what powers
        quick_command_klasses = [Search]

        autocleaning_analysis_klasses = [
            HeuristicFracs,
            ConvservativeCleaningGenops,
        ]
        #name is what shows up in the UI
        name = "conservative"
    return (ConservativeAC,)


@app.cell
def _(mo):
    mo.md(r"""
    # Configuring Buckaroo

    Here we create a new Buckaroo class with our combination of different AutoCleaningConfigs
    """)
    return


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import buckaroo
    from buckaroo import BuckarooInfiniteWidget
    import numpy as np
    from buckaroo.marimo_utils import (
        marimo_monkeypatch,
        BuckarooDataFrame as DataFrame,
    )
    from buckaroo.styling_helpers import obj_, float_, pinned_histogram
    from buckaroo.extension_utils import copy_extend
    from buckaroo.customizations.styling import DefaultMainStyling

    # this overrides pd.read_csv and pd.read_parquet to return BuckarooDataFrames which overrides displays as BuckarooWidget, not the default marimo table
    marimo_monkeypatch()
    return (
        BuckarooInfiniteWidget,
        DataFrame,
        DefaultMainStyling,
        copy_extend,
        float_,
        mo,
        obj_,
        pd,
        pinned_histogram,
    )


@app.cell
def _():
    from buckaroo.customizations.pd_autoclean_conf import AggressiveAC
    from buckaroo.customizations.pandas_commands import Command
    return AggressiveAC, Command


@app.cell
def _(
    AggressiveAC,
    BuckarooInfiniteWidget,
    ConservativeAC,
    DefaultMainStyling,
    copy_extend,
    dirty_df,
    float_,
    obj_,
    pinned_histogram,
):
    class CleaningDetailStyling(DefaultMainStyling):
        df_display_name = "cleaning_detail"
        pinned_rows = [
            obj_("dtype"),
            pinned_histogram(),
            float_("str_bool_frac"),
            float_("regular_int_parse_frac"),
            float_("strip_int_parse_frac"),
            float_("us_dates_frac"),
            obj_("cleaning_name"),
            obj_("null_count"),
        ]

    from buckaroo.customizations.pd_autoclean_conf import NoCleaningConf

    class MyAutocleaningBuckaroo(BuckarooInfiniteWidget):
        autoclean_conf = tuple([NoCleaningConf, AggressiveAC, ConservativeAC])
        analysis_klasses = copy_extend(
            BuckarooInfiniteWidget.analysis_klasses, CleaningDetailStyling
        )
    MyAutocleaningBuckaroo(dirty_df)
    return (MyAutocleaningBuckaroo,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
