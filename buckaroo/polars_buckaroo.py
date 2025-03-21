from io import BytesIO
import traceback

import polars as pl

from buckaroo.buckaroo_widget import BuckarooWidget, BuckarooInfiniteWidget, RawDFViewerWidget
from .customizations.polars_analysis import PL_Analysis_Klasses
from .pluggable_analysis_framework.polars_analysis_management import (
    PlDfStats)
from .serialization_utils import pd_to_obj
from .customizations.styling import DefaultSummaryStatsStyling, DefaultMainStyling
from .customizations.pl_autocleaning_conf import NoCleaningConfPl
from .dataflow.dataflow import Sampling
from .dataflow.autocleaning import PandasAutocleaning
from .dataflow.widget_extension_utils import configure_buckaroo

class PLSampling(Sampling):
    pre_limit = False

local_analysis_klasses = PL_Analysis_Klasses.copy()
local_analysis_klasses.extend(
    [DefaultSummaryStatsStyling,
     DefaultMainStyling

     ])


class PolarsAutocleaning(PandasAutocleaning):
    DFStatsKlass = PlDfStats
    
    @staticmethod
    def make_origs(raw_df, cleaned_df, cleaning_sd):
        clauses = []
        changed = 0
        for col, sd in cleaning_sd.items():
            if "add_orig" in sd:
                clauses.append(cleaned_df[col])
                clauses.append(raw_df[col].alias(col+"_orig"))
                changed += 1
            else:
                clauses.append(cleaned_df[col])
        if changed > 0:
            return cleaned_df.select(clauses)
        else:
            return cleaned_df

    
class PolarsBuckarooWidget(BuckarooWidget):
    """TODO: Add docstring here
    """
    analysis_klasses = local_analysis_klasses
    autocleaning_klass = PandasAutocleaning #override the base CustomizableDataFlow klass
    autoclean_conf = tuple([NoCleaningConfPl]) #override the base CustomizableDataFlow conf
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
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return pd_to_obj(self.sampling_klass.serialize_sample(df))
        return pd_to_obj(self.sampling_klass.serialize_sample(df.to_pandas()))


def to_parquet(df):
    # I don't like this copy.  modify to keep the same data with different names
    #df2 = df.copy()
    
    df.columns = [str(x) for x in df.columns]
    #obj_columns = df2.select_dtypes([pd.CategoricalDtype(), 'object']).columns.to_list()
    #encodings = {k:'json' for k in obj_columns}

    out = BytesIO()

    df.with_row_index().write_parquet(out, compression='uncompressed') #engine='fastparquet', object_encoding=encodings)
    out.seek(0)
    return out.read()


class PolarsBuckarooInfiniteWidget(PolarsBuckarooWidget, BuckarooInfiniteWidget):
    def _handle_payload_args(self, new_payload_args):
        start, end = new_payload_args['start'], new_payload_args['end']
        print("payload_args changed", start, end)
        _unused, processed_df, merged_sd = self.dataflow.widget_args_tuple
        if processed_df is None:
            return

        try:
            sort = new_payload_args.get('sort')
            if sort:
                sort_dir = new_payload_args.get('sort_direction')
                ascending = sort_dir == 'asc'
                sorted_df = processed_df.sort(sort, descending=not ascending)
                slice_df = sorted_df[start:end]
                #slice_df['index'] = slice_df.index
                self.send({ "type": "infinite_resp", 'key':new_payload_args, 'data':[], 'length':len(processed_df)}, [to_parquet(slice_df)])
            else:
                slice_df = processed_df[start:end]
                #slice_df['index'] = slice_df.index
                self.send({ "type": "infinite_resp", 'key':new_payload_args,
                            'data': [], 'length':len(processed_df)}, [to_parquet(slice_df) ])
    
                second_pa = new_payload_args.get('second_request')
                if not second_pa:
                    return
                
                extra_start, extra_end = second_pa.get('start'), second_pa.get('end')
                extra_df = processed_df[extra_start:extra_end]
                extra_df['index'] = extra_df.index
                self.send(
                    {"type": "infinite_resp", 'key':second_pa, 'data':[], 'length':len(processed_df)},
                    [to_parquet(extra_df)]
                )
        except Exception as e:
            print(e)
            stack_trace = traceback.format_exc()
            self.send({ "type": "infinite_resp", 'key':new_payload_args, 'data':[], 'error_info':stack_trace, 'length':0})
            raise


def PolarsDFViewer(df,
                   column_config_overrides=None,
                   extra_pinned_rows=None, pinned_rows=None,
                   extra_analysis_klasses=None, analysis_klasses=None,
                   ):
    """
    Display a Polars DataFrame with buckaroo styling and analysis, no extra UI pieces

    column_config_overrides allows targetted specific overriding of styling

    extra_pinned_rows adds pinned_rows of summary stats
    pinned_rows replaces the default pinned rows

    extra_analysis_klasses adds an analysis_klass
    analysis_klasses replaces default analysis_klass
    """
    BuckarooKls = configure_buckaroo(
        PolarsBuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    bw = BuckarooKls(df, column_config_overrides=column_config_overrides)
    dfv_config = bw.df_display_args['dfviewer_special']['df_viewer_config']
    df_data = bw.df_data_dict['main']
    summary_stats_data = bw.df_data_dict['all_stats']
    return RawDFViewerWidget(
        df_data=df_data, df_viewer_config=dfv_config, summary_stats_data=summary_stats_data)



