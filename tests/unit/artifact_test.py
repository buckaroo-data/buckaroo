import json
import base64
from io import BytesIO

import pandas as pd
import pytest

from buckaroo.artifact import (
    prepare_buckaroo_artifact,
    artifact_to_json,
    to_html,
    _df_to_parquet_b64_tagged,
)


simple_df = pd.DataFrame({
    'int_col': [1, 2, 3],
    'str_col': ['a', 'b', 'c'],
    'float_col': [1.1, 2.2, 3.3],
})


def _is_parquet_b64(val):
    """Check if value is a parquet b64 tagged payload."""
    return (
        isinstance(val, dict)
        and val.get('format') == 'parquet_b64'
        and isinstance(val.get('data'), str)
    )


def _decode_parquet_b64(tagged):
    """Decode a parquet b64 tagged payload to a DataFrame."""
    raw = base64.b64decode(tagged['data'])
    return pd.read_parquet(BytesIO(raw), engine='pyarrow')


class TestDfToParquetB64Tagged:
    def test_returns_tagged_format(self):
        result = _df_to_parquet_b64_tagged(simple_df)
        assert _is_parquet_b64(result)

    def test_roundtrip_preserves_shape(self):
        result = _df_to_parquet_b64_tagged(simple_df)
        decoded = _decode_parquet_b64(result)
        # prepare_df_for_serialization renames columns to a, b, c, ...
        # plus index and level_0
        assert 'index' in decoded.columns
        assert 'level_0' in decoded.columns
        assert len(decoded) == 3
        # Original 3 columns are renamed to a, b, c
        assert 'a' in decoded.columns
        assert 'b' in decoded.columns
        assert 'c' in decoded.columns

    def test_numeric_columns_preserved(self):
        result = _df_to_parquet_b64_tagged(simple_df)
        decoded = _decode_parquet_b64(result)
        # 'a' is int_col (first column)
        assert list(decoded['a']) == [1, 2, 3]

    def test_string_columns_json_encoded(self):
        """String columns are JSON-encoded per cell for JS decoding."""
        result = _df_to_parquet_b64_tagged(simple_df)
        decoded = _decode_parquet_b64(result)
        # 'b' is str_col (second column), JSON-encoded: 'a' -> '"a"'
        for val in decoded['b']:
            parsed = json.loads(val)
            assert isinstance(parsed, str)
        assert json.loads(decoded['b'].iloc[0]) == 'a'


class TestPrepareBuckarooArtifact:
    def test_returns_three_keys(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        assert 'df_data' in artifact
        assert 'df_viewer_config' in artifact
        assert 'summary_stats_data' in artifact

    def test_df_data_is_parquet_b64(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        assert _is_parquet_b64(artifact['df_data'])

    def test_summary_stats_is_parquet_b64(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        assert _is_parquet_b64(artifact['summary_stats_data'])

    def test_df_viewer_config_is_dict(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        config = artifact['df_viewer_config']
        assert isinstance(config, dict)
        assert 'column_config' in config
        assert 'pinned_rows' in config

    def test_artifact_json_serializable(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        json_str = artifact_to_json(artifact)
        roundtripped = json.loads(json_str)
        assert _is_parquet_b64(roundtripped['df_data'])
        assert _is_parquet_b64(roundtripped['summary_stats_data'])

    def test_df_data_decodable(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        decoded = _decode_parquet_b64(artifact['df_data'])
        assert len(decoded) == 3

    def test_summary_stats_decodable(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        decoded = _decode_parquet_b64(artifact['summary_stats_data'])
        assert len(decoded) > 0  # should have stat rows like dtype, mean, etc.

    def test_with_column_config_overrides(self):
        overrides = {'int_col': {'displayer_args': {'displayer': 'string'}}}
        artifact = prepare_buckaroo_artifact(simple_df, column_config_overrides=overrides)
        assert _is_parquet_b64(artifact['df_data'])


class TestBuckarooEmbedType:
    def test_embed_type_dfviewer_default(self):
        artifact = prepare_buckaroo_artifact(simple_df)
        assert artifact['embed_type'] == 'DFViewer'
        assert 'df_display_args' not in artifact
        assert 'df_data_dict' not in artifact

    def test_embed_type_buckaroo(self):
        artifact = prepare_buckaroo_artifact(simple_df, embed_type='Buckaroo')
        assert artifact['embed_type'] == 'Buckaroo'
        assert 'df_display_args' in artifact
        assert 'df_data_dict' in artifact
        assert 'df_meta' in artifact
        assert 'buckaroo_options' in artifact
        assert 'buckaroo_state' in artifact

    def test_buckaroo_df_display_args_has_keys(self):
        artifact = prepare_buckaroo_artifact(simple_df, embed_type='Buckaroo')
        dda = artifact['df_display_args']
        assert isinstance(dda, dict)
        assert len(dda) > 0
        for key, val in dda.items():
            assert 'df_viewer_config' in val
            assert 'data_key' in val
            assert 'summary_stats_key' in val

    def test_buckaroo_df_data_dict_has_main(self):
        artifact = prepare_buckaroo_artifact(simple_df, embed_type='Buckaroo')
        assert 'main' in artifact['df_data_dict']
        assert _is_parquet_b64(artifact['df_data_dict']['main'])

    def test_buckaroo_json_serializable(self):
        artifact = prepare_buckaroo_artifact(simple_df, embed_type='Buckaroo')
        json_str = artifact_to_json(artifact)
        roundtripped = json.loads(json_str)
        assert roundtripped['embed_type'] == 'Buckaroo'
        assert 'df_display_args' in roundtripped

    def test_invalid_embed_type_raises(self):
        with pytest.raises(ValueError, match="embed_type"):
            prepare_buckaroo_artifact(simple_df, embed_type='Invalid')


class TestToHtml:
    def test_returns_html_string(self):
        html = to_html(simple_df)
        assert '<!DOCTYPE html>' in html
        assert 'buckaroo-data' in html
        assert 'application/json' in html
        assert 'static-embed.js' in html

    def test_custom_title(self):
        html = to_html(simple_df, title="My Table")
        assert '<title>My Table</title>' in html

    def test_artifact_embedded_as_json(self):
        html = to_html(simple_df)
        assert 'parquet_b64' in html


class TestWeirdTypesParquetRoundtrip:
    """Parquet b64 encoding must produce standard types that hyparquet can decode.

    Period, Interval, and Timedelta are pandas-specific Arrow extension types
    that hyparquet (the JS parquet reader) doesn't understand. They must be
    coerced to strings before parquet serialization.
    """

    def test_period_coerced_to_string(self):
        df = pd.DataFrame({
            'period': pd.Series(pd.period_range('2021-01', periods=3, freq='M')),
        })
        result = _df_to_parquet_b64_tagged(df)
        decoded = _decode_parquet_b64(result)
        # Column 'a' (renamed from 'period') should be string, not PeriodDtype
        assert not isinstance(decoded['a'].dtype, pd.PeriodDtype), \
            f"period column was not coerced: dtype={decoded['a'].dtype}"

    def test_interval_coerced_to_string(self):
        df = pd.DataFrame({
            'interval': pd.Series(
                pd.arrays.IntervalArray.from_breaks([0, 1, 2, 3])),
        })
        result = _df_to_parquet_b64_tagged(df)
        decoded = _decode_parquet_b64(result)
        assert not isinstance(decoded['a'].dtype, pd.IntervalDtype), \
            f"interval column was not coerced: dtype={decoded['a'].dtype}"

    def test_timedelta_coerced_to_string(self):
        df = pd.DataFrame({
            'td': pd.to_timedelta(['1 days', '2 days', '3 days']),
        })
        result = _df_to_parquet_b64_tagged(df)
        decoded = _decode_parquet_b64(result)
        # Should not be timedelta64 — hyparquet reads duration[ns] as raw ints
        assert not pd.api.types.is_timedelta64_dtype(decoded['a'].dtype), \
            f"timedelta column was not coerced: dtype={decoded['a'].dtype}"

    def test_weird_types_df_full_roundtrip(self):
        """The full DDD weird types DataFrame should serialize without extension types."""
        from buckaroo.ddd_library import df_with_weird_types
        df = df_with_weird_types()
        artifact = prepare_buckaroo_artifact(df, embed_type='Buckaroo')
        decoded = _decode_parquet_b64(artifact['df_data'])
        for col in decoded.columns:
            dtype = decoded[col].dtype
            assert not isinstance(dtype, (pd.PeriodDtype, pd.IntervalDtype)), \
                f"column {col} has non-standard dtype: {dtype}"
            assert not pd.api.types.is_timedelta64_dtype(dtype), \
                f"column {col} has timedelta dtype: {dtype}"


class TestPolarsSupport:
    def test_polars_dataframe(self):
        pl = pytest.importorskip("polars")
        df = pl.DataFrame({
            'int_col': [1, 2, 3],
            'str_col': ['a', 'b', 'c'],
        })
        artifact = prepare_buckaroo_artifact(df)
        assert _is_parquet_b64(artifact['df_data'])
        assert _is_parquet_b64(artifact['summary_stats_data'])
        assert isinstance(artifact['df_viewer_config'], dict)


class TestFilePath:
    def test_csv_file(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        simple_df.to_csv(csv_file, index=False)
        artifact = prepare_buckaroo_artifact(str(csv_file))
        assert _is_parquet_b64(artifact['df_data'])
        decoded = _decode_parquet_b64(artifact['df_data'])
        assert len(decoded) == 3
