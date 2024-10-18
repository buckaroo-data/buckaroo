import polars as pl
#import numpy as np

from ..jlisp.lisp_utils import s
#from ..jlisp.configure_utils import configure_buckaroo
#from ..auto_clean.cleaning_commands import (to_bool, to_datetime, to_int, to_float, to_string)

class Command(object):
    @staticmethod 
    def transform(df, col, val):
        return df.with_columns(pl.col(col).fill_null(val))
        return df

    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df = df.with_columns(pl.col('%s').fill_null(%r))" % (col, val)

class FillNA(Command):
    #argument_names = ["df", "col", "fill_val"]
    command_default = [s('fillna'), s('df'), "col", 8]
    command_pattern = [[3, 'fillVal', 'type', 'integer']]

    @staticmethod 
    def transform(df, col, val):
        return df.with_columns(pl.col(col).fill_null(val))
        return df

    @staticmethod 
    def transform_to_py(df, col, val):
        return "    df = df.with_columns(pl.col('%s').fill_null(%r))" % (col, val)

class NoOp(Command):
    #used for testing command stuff
    command_default = [s('noop'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    #noop"
    
class PlSafeInt(Command):
    command_default = [s('safe_int'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        return df.with_columns(pl.col(col).cast(pl.Int64, strict=False))
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df = df.with_columns(pl.col('%s').cast(pl.Int64, strict=False))" % (col)

class DropCol(Command):
    #argument_names = ["df", "col"]
    command_default = [s('dropcol'), s('df'), "col"]
    command_pattern = [None]

    @staticmethod 
    def transform(df, col):
        return df.drop(col)
        return df

    @staticmethod 
    def transform_to_py(df, col):
        return "    df.drop_in_place('%s')" % col


class GroupBy(Command):
    command_default = [s("groupby"), s('df'), 'col', {}]
    command_pattern = [[3, 'colMap', 'colEnum', ['null', 'sum', 'mean', 'median', 'count']]]
    @staticmethod 
    def transform(df, col, col_spec):
        agg_clauses = []
        for k, v in col_spec.items():
            if v == "sum":
                agg_clauses.append(pl.col(k).sum().alias("%s(sum)" % k))
            elif v == "mean":
                agg_clauses.append(pl.col(k).mean().alias("%s(mean)" % k))
            elif v == "median":
                agg_clauses.append(pl.col(k).median.alias("%s(median)" % k))
            elif v == "count":
                agg_clauses.append(pl.col(k).drop_nulls().count().alias("%s(count)" % k))

        q = (
            df
            .lazy()
            .group_by(by=col)
            .agg(*agg_clauses)
            .sort(col, descending=True)
        )
        return q.collect()



    @staticmethod 
    def transform_to_py(df, col, col_spec):
        agg_clauses = []
        for k, v in col_spec.items():
            if v == "sum":
                agg_clauses.append("    pl.col('%s').sum().alias('%s(sum)')"  % (k, k))
            elif v == "mean":
                agg_clauses.append("    pl.col('%s').mean().alias('%s(mean)')"  % (k, k))
            elif v == "median":
                agg_clauses.append("    pl.col('%s').median().alias('%s(median)')"  % (k, k))
            elif v == "count":
                agg_clauses.append("    pl.col('%s').drop_nulls().count().alias('%s(count)')"  % (k, k))
        full_agg_text = ",\n".join(agg_clauses)
        command_template = """
    q = (
         df
        .lazy()
        .group_by(by='%s')
        .agg(%s)
        .sort('%s', descending=True)
        )
    df = q.collect()
        """
        return command_template % (col, full_agg_text, col)



class Search(Command):
    command_default = [s('search'), s('df'), "col", ""]
    command_pattern = [[3, 'term', 'type', 'string']]
    quick_args_pattern = [[3, 'term', 'type', 'string']]

    @staticmethod 
    def transform(df, col, val):
        return df.filter(pl.any_horizontal(pl.col(pl.String).str.contains(val)))


    @staticmethod 
    def transform_to_py(df, col, val):
        return f"    df = df.filter(pl.any_horizontal(pl.col(pl.String).str.contains('{val}')))"
