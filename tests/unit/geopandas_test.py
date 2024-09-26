from buckaroo.geopandas_buckaroo import GeopandasSVGBuckarooWidget, GeopandasBuckarooWidget
from .fixtures import (DistinctCount)
import geopandas



def xtest_basic_instantiation():
    """ test that GeopandasBuckarooWidget can instantiate without an error"""
    world_df = geopandas.read_file(geopandas.datasets.get_path('naturalearth_lowres'))
    GeopandasBuckarooWidget(world_df)

def xtest_summary_stats():
    """
    test that summary stats serialize properly
    """
    class SimpleGeoBW(GeopandasBuckarooWidget):
        analysis_klasses = [DistinctCount]
        pinned_rows = []
    world_df = geopandas.read_file(geopandas.datasets.get_path('naturalearth_lowres'))
    w = SimpleGeoBW(world_df[:3])
    assert w.df_data_dict['all_stats'] == [
        {'continent': 2,
         'gdp_md_est': 3,
         'geometry': 3,
         'index': 'distinct_count',
         'iso_a3': 3,
         'name': 3,
         'pop_est': 3},
    ]

def xtest_svg():
    """ test that GeopandasSVGBuckarooWidget can instantiate without an error"""
    world_df = geopandas.read_file(geopandas.datasets.get_path('naturalearth_lowres'))
    GeopandasSVGBuckarooWidget(world_df[:10])
