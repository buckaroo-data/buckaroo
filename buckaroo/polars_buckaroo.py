import polars as pl
from buckaroo.buckaroo_widget import BuckarooWidget
from .customizations.polars_analysis import PL_Analysis_Klasses
from .pluggable_analysis_framework.polars_analysis_management import (
    PlDfStats)
from .serialization_utils import pd_to_obj
from buckaroo.customizations.polars_commands import (
    DropCol, FillNA, GroupBy #, OneHot, GroupBy, reindex
)
from .customizations.styling import DefaultSummaryStatsStyling, DefaultMainStyling
from .dataflow import Sampling


class PLSampling(Sampling):
    pre_limit = False

local_analysis_klasses = PL_Analysis_Klasses.copy()
local_analysis_klasses.extend(
    [DefaultSummaryStatsStyling, DefaultMainStyling])

class PolarsBuckarooWidget(BuckarooWidget):
    """TODO: Add docstring here
    """
    command_classes = [DropCol, FillNA, GroupBy]
    analysis_klasses = local_analysis_klasses
    DFStatsClass = PlDfStats
    sampling_klass = PLSampling

    def _sd_to_jsondf(self, sd):
        """exists so this can be overriden for polars  """
        import pandas as pd
        temp_sd = sd.copy()

        #FIXME add actual test around weird index behavior
        # if 'index' in temp_sd:
        #     del temp_sd['index']
        return pd_to_obj(pd.DataFrame(temp_sd))

    def _build_error_dataframe(self, e):
        return pl.DataFrame({'err': [str(e)]})

    def _df_to_obj(self, df):
        # I want to this, but then row numbers are lost
        #return pd_to_obj(self.sampling_klass.serialize_sample(df).to_pandas())
        return pd_to_obj(self.sampling_klass.serialize_sample(df.to_pandas()))

