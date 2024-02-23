from buckaroo.customizations.styling import (DefaultMainStyling)
from buckaroo.buckaroo_widget import RawDFViewerWidget, BuckarooWidget

def find_most_specific_styling(klasses, df_display_name='main'):
    """if we have multiple styling klasses, all of which extend StylingAnalysis keyed to df_display_name='main'
    we want a deterministic result for which one is the called class to provide styling for that key

    if B extends A, B is more specific.

    Since most class extension for styling will work by extending
    DefaultMainStyling, try to follow the user's intent by making sure
    the most specific class is chosen

    https://stackoverflow.com/questions/23660447/how-can-i-sort-a-list-of-python-classes-by-inheritance-depth
    """
    styling_klasses = filter(lambda x: issubclass(x, DefaultMainStyling), klasses)
    klasses_by_depth = sorted(styling_klasses, key=lambda x: len(x.__mro__))
    return klasses_by_depth[-1]

class InvalidArgumentException(Exception):
    pass
def analysis_extend(
        BaseBuckarooKls,
        extra_analysis_klasses=None, analysis_klasses=None):

    # In this case we are going to extend PolarsBuckarooWidget so we
    # can take this combination with us
    base_a_klasses = BaseBuckarooKls.analysis_klasses.copy()
    if extra_analysis_klasses:
        if analysis_klasses is not None:
            raise InvalidArgumentException(
                "Must specify either extra_analysis_klasses or analysis_klasses, not both")
        base_a_klasses.extend(extra_analysis_klasses)
    elif analysis_klasses:
        base_a_klasses = analysis_klasses
    return base_a_klasses

def get_styling_analysis(
        BaseStylingKlass,
        extra_pinned_rows=None, pinned_rows=None):

    base_pinned_rows = BaseStylingKlass.pinned_rows.copy()
    if extra_pinned_rows:
        if pinned_rows is not None:
            raise InvalidArgumentException(
                "Must specify either extra_pinned_rows or pinned_rows, not both")
        base_pinned_rows.extend(extra_pinned_rows)
    elif pinned_rows is not None: # is not None accomodates empty list
        base_pinned_rows = pinned_rows

    class SyntheticStyling(BaseStylingKlass):
        pinned_rows = base_pinned_rows
        df_display_name = "dfviewer_special"

    return SyntheticStyling

        
def configure_buckaroo(
        BaseBuckarooKls,
        extra_pinned_rows=None, pinned_rows=None,
        extra_analysis_klasses=None, analysis_klasses=None):
    """Used to instantiate a synthetic Buckaroo class with easier extension methods.

    It seemed more straight forward to write this as a completely
    separate function vs a classmethod so that things are clear vs
    inheritance
    """


    a_klasses = analysis_extend(
        BaseBuckarooKls,
        extra_analysis_klasses, analysis_klasses)
        
    #there could possibly be another way of picking off the styling
    #klass vs just knowing that it's default BaseStylingKls
    #BaseStylingKls = DefaultMainStyling 
    BaseStylingKls = find_most_specific_styling(a_klasses)

    special_styling_analysis_klass = get_styling_analysis(
        BaseStylingKls, extra_pinned_rows, pinned_rows)

    a_klasses.append(special_styling_analysis_klass)

    class TempBuckarooWidget(BaseBuckarooKls):
        analysis_klasses = a_klasses
    return TempBuckarooWidget
        


def DFViewer(df,
             column_config_overrides=None,
             extra_pinned_rows=None, pinned_rows=None,
             extra_analysis_klasses=None, analysis_klasses=None):
    """
    Display a DataFrame with buckaroo styling and analysis, no extra UI pieces

    column_config_overrides allows targetted specific overriding of styling

    extra_pinned_rows adds pinned_rows of summary stats
    pinned_rows replaces the default pinned rows

    extra_analysis_klasses adds an analysis_klass
    analysis_klasses replaces default analysis_klass
    """
    BuckarooKls = configure_buckaroo(
        BuckarooWidget,
        extra_pinned_rows=extra_pinned_rows, pinned_rows=pinned_rows,
        extra_analysis_klasses=extra_analysis_klasses, analysis_klasses=analysis_klasses)

    bw = BuckarooKls(df, column_config_overrides=column_config_overrides)
    dfv_config = bw.df_display_args['dfviewer_special']['df_viewer_config']
    df_data = bw.df_data_dict['main']
    summary_stats_data = bw.df_data_dict['all_stats']
    return RawDFViewerWidget(
        df_data=df_data, df_viewer_config=dfv_config, summary_stats_data=summary_stats_data)


