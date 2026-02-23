from typing import Tuple, Dict as TDict, Any as TAny

import pandas as pd
from typing_extensions import override

from buckaroo.pluggable_analysis_framework.col_analysis import SDType
from buckaroo.pluggable_analysis_framework.df_stats_v2 import DfStatsV2
from ..serialization_utils import pd_to_obj
from .dataflow import CustomizableDataflow


class PandasCustomizableDataflow(CustomizableDataflow):
    """Concrete pandas implementation of CustomizableDataflow."""

    DFStatsClass = DfStatsV2

    @override
    def _compute_processed_result(self, cleaned_df, post_processing_method):
        if post_processing_method == '':
            return (cleaned_df, {})
        else:
            post_analysis = self.post_processing_klasses[post_processing_method]
            try:
                ret_df, sd = post_analysis.post_process_df(cleaned_df)
                return (ret_df, sd)
            except Exception as e:
                return (self._build_error_dataframe(e), {})

    @override
    def _build_error_dataframe(self, e):
        return pd.DataFrame({'err': [str(e)]})

    @override
    def _get_summary_sd(self, processed_df) -> Tuple[SDType, TDict[str, TAny]]:
        stats = self.DFStatsClass(
            processed_df,
            self.analysis_klasses,
            self.df_name, debug=self.debug)
        sdf = stats.sdf
        if stats.errs:
            if self.debug:
                raise Exception("Error executing analysis")
            else:
                return {}, stats.errs
        else:
            return sdf, {}

    @override
    def _df_to_obj(self, df) -> TDict[str, TAny]:
        return pd_to_obj(self.sampling_klass.serialize_sample(df))
