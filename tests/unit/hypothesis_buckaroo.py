import hypothesis

import buckaroo
from hypothesis import strategies as st
from hypothesis.extra.pandas import data_frames, column


@hypothesis.settings(deadline=10_000)
@hypothesis.given(
    # TODO: write strategy to support n-Columns
    df=st.one_of(data_frames(columns=[column(elements=st.integers())]),
                 data_frames(columns=[column(elements=st.floats())]),
                 data_frames(columns=[column(elements=st.text())]),
                 data_frames(columns=[column(elements=
                                             st.dictionaries(st.text(), st.integers()))]),
                 data_frames(columns=[column(elements=
                                             st.lists(st.text()))])),
    sampled=st.booleans(),
    summaryStats=st.booleans(),
    reorderdColumns=st.booleans(),
    showCommands=st.booleans(),
    postProcessingF=st.none(),
)
def test_fuzz_BuckarooWidget(
        df,
        sampled,
        summaryStats,
        reorderdColumns,
        showCommands,
        postProcessingF,
):

    #debug=True will cause an analysis error to throw an error,
    #auto_clean is tempermental and not turned on by default
    buckaroo.BuckarooWidget(
        df=df,
        sampled=sampled,
        summaryStats=summaryStats,
        reorderdColumns=reorderdColumns,
        showCommands=showCommands,
        auto_clean=False,
        postProcessingF=postProcessingF,
        debug=True
    )
