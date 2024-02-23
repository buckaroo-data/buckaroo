from buckaroo import BuckarooWidget
from buckaroo.buckaroo_widget import RawDFViewerWidget
from buckaroo.dataflow.widget_extension_utils import configure_buckaroo

def SolaraDFViewer(df, column_config_overrides=None,
                    extra_pinned_rows=None, pinned_rows=None,
                    extra_analysis_klasses=None, analysis_klasses=None):
    import reacton    
    BuckarooKls = configure_buckaroo(
        BuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    bw = BuckarooKls(df, column_config_overrides=column_config_overrides)
    dfv_config = bw.df_display_args['dfviewer_special']['df_viewer_config']
    df_data = bw.df_data_dict['main']
    summary_stats_data = bw.df_data_dict['all_stats']

    comp = reacton.core.ComponentWidget(widget=RawDFViewerWidget)
    
    element_kwargs = dict(df_data=df_data, df_viewer_config=dfv_config, summary_stats_data=summary_stats_data)

    return reacton.core.Element(comp, kwargs=element_kwargs)

def SolaraBuckarooWidget(df, column_config_overrides=None,
                    extra_pinned_rows=None, pinned_rows=None,
                    extra_analysis_klasses=None, analysis_klasses=None):
    import reacton    
    BuckarooKls = configure_buckaroo(
        BuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    comp = reacton.core.ComponentWidget(widget=BuckarooKls)
    return reacton.core.Element(comp, df=df, column_config_overrides=column_config_overrides)

def SolaraPolarsDFViewer(df, column_config_overrides=None,
                    extra_pinned_rows=None, pinned_rows=None,
                    extra_analysis_klasses=None, analysis_klasses=None):
    import reacton
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget
    BuckarooKls = configure_buckaroo(
        PolarsBuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    bw = BuckarooKls(df, column_config_overrides=column_config_overrides)
    dfv_config = bw.df_display_args['dfviewer_special']['df_viewer_config']
    df_data = bw.df_data_dict['main']
    summary_stats_data = bw.df_data_dict['all_stats']

    comp = reacton.core.ComponentWidget(widget=RawDFViewerWidget)
    
    element_kwargs = dict(df_data=df_data, df_viewer_config=dfv_config, summary_stats_data=summary_stats_data)

    return reacton.core.Element(comp, kwargs=element_kwargs)

def SolaraPolarsBuckarooWidget(df, column_config_overrides=None,
                    extra_pinned_rows=None, pinned_rows=None,
                    extra_analysis_klasses=None, analysis_klasses=None):
    import reacton
    from buckaroo.polars_buckaroo import PolarsBuckarooWidget
    BuckarooKls = configure_buckaroo(
        PolarsBuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    comp = reacton.core.ComponentWidget(widget=BuckarooKls)
    return reacton.core.Element(comp, df=df, column_config_overrides=column_config_overrides)
