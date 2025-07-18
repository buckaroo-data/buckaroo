import pytest
from buckaroo.dataflow.widget_extension_utils import (
    find_most_specific_styling, analysis_extend, get_styling_analysis,
    InvalidArgumentException,
    configure_buckaroo)
from buckaroo.customizations.styling import (DefaultMainStyling)
from buckaroo.buckaroo_widget import BuckarooWidget
from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis
from buckaroo.styling_helpers import obj_

def foo():
    print(analysis_extend, get_styling_analysis, configure_buckaroo)

class Custom_1(ColAnalysis):
    pass

class CustomStyling(DefaultMainStyling):
    pinned_rows= ['foo']

class ExtendedCustomStyling(CustomStyling):
    pinned_rows= ['foo', 'bar']

def test_find_most_specific_styling():
    # Custom_1 doesn't extend DefaultMain, it looses
    assert find_most_specific_styling([Custom_1, DefaultMainStyling]) == DefaultMainStyling
    #order shouldn't matter
    assert find_most_specific_styling([DefaultMainStyling, Custom_1]) == DefaultMainStyling

    assert find_most_specific_styling([CustomStyling, DefaultMainStyling]) == CustomStyling
    assert find_most_specific_styling([DefaultMainStyling, CustomStyling]) == CustomStyling

    assert find_most_specific_styling([ExtendedCustomStyling, CustomStyling, DefaultMainStyling]) == ExtendedCustomStyling
    assert find_most_specific_styling([DefaultMainStyling, CustomStyling, ExtendedCustomStyling]) == ExtendedCustomStyling

def test_analysis_extend():
    #Custom_1 doesn't extend BaseStylingKlass, so it won't work
    assert [Custom_1] == analysis_extend(BuckarooWidget, analysis_klasses=[Custom_1])

    base_len = len(BuckarooWidget.analysis_klasses)
    extra_kls_lst = analysis_extend(BuckarooWidget, extra_analysis_klasses=[Custom_1])
    assert Custom_1 in extra_kls_lst
    assert len(extra_kls_lst) == (base_len) + 1

    with pytest.raises(InvalidArgumentException):
        analysis_extend(BuckarooWidget, extra_analysis_klasses=[Custom_1], analysis_klasses=[ExtendedCustomStyling])


foo_row = obj_('foo')

def test_get_styling_analysis():
    base_pinned_row_len = len(DefaultMainStyling.pinned_rows)
    ExtraFooStyling = get_styling_analysis(
        DefaultMainStyling,
        extra_pinned_rows=[foo_row])

    assert foo_row in ExtraFooStyling.pinned_rows
    assert len(ExtraFooStyling.pinned_rows) == (base_pinned_row_len + 1)

    ReplacePinnedStyling = get_styling_analysis(DefaultMainStyling, pinned_rows=[foo_row])
    assert ReplacePinnedStyling.pinned_rows == [foo_row]
    with pytest.raises(InvalidArgumentException):
        get_styling_analysis(DefaultMainStyling, extra_pinned_rows=[1], pinned_rows=[2])

def test_configure_buckaroo_extra():

    ExtraBuckaroo = configure_buckaroo(
        BuckarooWidget, extra_pinned_rows=[foo_row], extra_analysis_klasses=[Custom_1])
    SyntheticStyling = [kls for kls in ExtraBuckaroo.analysis_klasses if kls.__name__ == 'SyntheticStyling'][0]

    base_pinned_row_len = len(DefaultMainStyling.pinned_rows)

    assert foo_row in SyntheticStyling.pinned_rows
    assert len(SyntheticStyling.pinned_rows) == (base_pinned_row_len + 1)

    assert Custom_1 in ExtraBuckaroo.analysis_klasses


def test_configure_buckaroo_replace():
    
    ReplaceBuckaroo = configure_buckaroo(
        BuckarooWidget, analysis_klasses=[Custom_1, DefaultMainStyling],
        pinned_rows=[foo_row])

    #bad things will happen if there isn't a Styling, but I'd caveat empetor for that
    
    SyntheticStyling = [kls for kls in ReplaceBuckaroo.analysis_klasses if kls.__name__ == 'SyntheticStyling'][0]

    assert SyntheticStyling.pinned_rows == [foo_row]

    assert len(ReplaceBuckaroo.analysis_klasses) == 3
    assert Custom_1 in ReplaceBuckaroo.analysis_klasses

                       
