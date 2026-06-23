"""Tests for encode_df — the single Python-side dataframe payload encoder.

encode_df picks the envelope format from the transport capability
(``comm`` → buffer side-channel, ``static`` → inline base64) with an
explicit ``fmt`` override, and returns ``(envelope_dict, buffers)``.
See docs/plans/unified-df-transport.md.
"""
import base64
from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq

from buckaroo.serialization_utils import (encode_df, buffer_payload, b64_payload, resolve_summary_stats_payload, sd_to_parquet_b64)


def _df():
    return pd.DataFrame({'nums': [1, 2, 3], 'name': ['a', 'b', 'c']})


def test_comm_transport_yields_parquet_buffer_envelope_and_one_buffer():
    env, buffers = encode_df(_df(), 'comm')
    assert env['format'] == 'parquet_buffer'
    assert env['buffer_index'] == 0
    assert len(buffers) == 1
    assert isinstance(buffers[0], (bytes, bytearray))
    assert len(buffers[0]) > 0


def test_static_transport_yields_parquet_b64_envelope_and_no_buffers():
    env, buffers = encode_df(_df(), 'static')
    assert env['format'] == 'parquet_b64'
    assert isinstance(env['data'], str)
    assert buffers == []
    # the b64 string decodes to a valid parquet table
    table = pq.read_table(BytesIO(base64.b64decode(env['data'])))
    assert table.num_rows == 3


def test_json_fmt_override_yields_record_array_inline():
    env, buffers = encode_df(_df(), 'comm', fmt='json')
    assert env['format'] == 'json'
    assert buffers == []
    assert isinstance(env['data'], list)
    assert len(env['data']) == 3


def test_layout_rides_on_the_envelope_not_baked_into_format():
    env, _ = encode_df(_df(), 'static', layout='wide')
    assert env['format'] == 'parquet_b64'
    assert env['layout'] == 'wide'
    env2, _ = encode_df(_df(), 'comm', layout='wide')
    assert env2['format'] == 'parquet_buffer'
    assert env2['layout'] == 'wide'


def test_no_layout_key_when_not_wide():
    env, _ = encode_df(_df(), 'comm')
    assert 'layout' not in env


def test_comm_buffer_round_trips_to_the_same_rows():
    env, buffers = encode_df(_df(), 'comm')
    table = pq.read_table(BytesIO(buffers[0]))
    d = table.to_pydict()
    # columns are renamed a,b... by prepare_df_for_serialization
    assert d['a'] == [1, 2, 3]


def test_buffer_payload_wraps_precomputed_bytes():
    env, buffers = buffer_payload(b'PAR1fake', layout='wide')
    assert env == {'format': 'parquet_buffer', 'buffer_index': 0, 'layout': 'wide'}
    assert buffers == [b'PAR1fake']


def test_b64_payload_wraps_precomputed_bytes():
    env, buffers = b64_payload(b'PAR1fake')
    assert env['format'] == 'parquet_b64'
    assert base64.b64decode(env['data']) == b'PAR1fake'
    assert buffers == []


def test_resolve_summary_stats_still_decodes_wide_payload_from_encoder():
    """sd_to_parquet_b64 now routes its envelope through b64_payload; the
    decoder must still pivot it back to row-form DFData."""
    sd = {'a': {'mean': 5.0, 'dtype': 'float64'},
          'b': {'mean': 2.0, 'dtype': 'int64'}}
    payload = sd_to_parquet_b64(sd)
    assert payload['format'] == 'parquet_b64'
    assert payload['layout'] == 'wide'
    rows = resolve_summary_stats_payload(payload)
    mean_row = next(r for r in rows if r['index'] == 'mean')
    assert mean_row['a'] == 5.0
    assert mean_row['b'] == 2.0
    dtype_row = next(r for r in rows if r['index'] == 'dtype')
    assert dtype_row['a'] == 'float64'
