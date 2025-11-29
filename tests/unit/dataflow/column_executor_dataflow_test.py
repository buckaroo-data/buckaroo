import polars as pl
from polars import functions as F

from buckaroo.dataflow.column_executor_dataflow import ColumnExecutorDataflow
from buckaroo.pluggable_analysis_framework.polars_analysis_management import PolarsAnalysis
from buckaroo.pluggable_analysis_framework.utils import json_postfix
from buckaroo.dataflow.styling_core import merge_sds


class SelectOnlyAnalysis(PolarsAnalysis):
    """
    Simple analysis used in existing polars tests; provides a few aggregate measures.
    """
    select_clauses = [
        F.all().null_count().name.map(json_postfix('null_count')),
        F.all().mean().name.map(json_postfix('mean')),
        F.all().quantile(.99).name.map(json_postfix('quin99')),
    ]


def test_init_and_df_meta_lazy():
    df = pl.DataFrame({'x': [1, 2, 3], 'y': ['a', 'b', 'c']})
    ldf = df.lazy()
    cdf = ColumnExecutorDataflow(ldf)
    assert cdf.df_meta['columns'] == 2
    assert cdf.df_meta['total_rows'] == 3
    # no-op configs present
    assert cdf.command_config == {}
    assert cdf.quick_command_args == {}
    assert cdf.cleaning_method == ''
    assert cdf.post_processing_method == ''


def test_add_analysis_and_dedup():
    df = pl.DataFrame({'x': [1, 2, 3]})
    ldf = df.lazy()
    cdf = ColumnExecutorDataflow(ldf, analysis_klasses=[SelectOnlyAnalysis])
    # Adding same analysis should deduplicate by cname
    cdf.add_analysis(SelectOnlyAnalysis)
    names = sorted([a.cname() for a in cdf.analysis_klasses])
    assert names.count(SelectOnlyAnalysis.cname()) == 1


def test_compute_summary_with_executor_and_merge():
    test_df = pl.DataFrame({'normal_int_series': [1, 2, 3, 4]})
    ldf = test_df.lazy()
    cdf = ColumnExecutorDataflow(ldf, analysis_klasses=[SelectOnlyAnalysis])

    cdf.compute_summary_with_executor()
    # Expect rewritten key 'a' with our measures plus orig/rewritten names
    assert 'a' in cdf.summary_sd
    a_meta = cdf.summary_sd['a']
    assert a_meta['orig_col_name'] == 'normal_int_series'
    assert a_meta['rewritten_col_name'] == 'a'
    # Measures provided by SelectOnlyAnalysis
    assert a_meta['null_count'] == 0
    assert a_meta['mean'] == 2.5
    assert a_meta['quin99'] == 4.0

    # Verify merged_sd mirrors summary when cleaned/processed are empty
    assert cdf.merged_sd == cdf.summary_sd

    # Now augment cleaned_sd and processed_sd and recompute merge (no helper methods; set directly)
    cdf.cleaned_sd = {'a': {'cleaned_flag': True}}
    cdf.processed_sd = {'a': {'processed_flag': True}}
    cdf.merged_sd = merge_sds(cdf.cleaned_sd or {}, cdf.summary_sd or {}, cdf.processed_sd or {})
    assert cdf.merged_sd['a']['cleaned_flag'] is True
    assert cdf.merged_sd['a']['processed_flag'] is True
    # original summary fields still present
    assert cdf.merged_sd['a']['mean'] == 2.5

