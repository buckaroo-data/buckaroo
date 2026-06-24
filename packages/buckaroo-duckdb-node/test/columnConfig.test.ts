import { describe, it, expect } from 'vitest';
import { duckTypeToColType, displayerForColType } from '../src/duckTypes';
import {
  buildColumnConfig,
  buildDfViewerConfig,
  buildPinnedRows,
  V1_PINNED_STATS,
} from '../src/columnConfig';
import { buildRenamePlan } from '../src/rename';
import type { DescribeRow } from '../src/DuckSource';

describe('duckTypeToColType', () => {
  it.each([
    ['BIGINT', 'integer'],
    ['INTEGER', 'integer'],
    ['UTINYINT', 'integer'],
    ['DOUBLE', 'float'],
    ['DECIMAL(38,9)', 'float'],
    ['REAL', 'float'],
    ['VARCHAR', 'string'],
    ['BOOLEAN', 'string'],
    ['DATE', 'datetime'],
    ['TIMESTAMP', 'datetime'],
    ['TIMESTAMP WITH TIME ZONE', 'datetime'],
    ['INTEGER[]', 'obj'],
    ['STRUCT(a INT)', 'obj'],
  ])('%s → %s', (duckType, expected) => {
    expect(duckTypeToColType(duckType)).toBe(expected);
  });
});

describe('displayerForColType (DefaultMainStyling parity)', () => {
  it('renders integers via float with 0 fraction digits', () => {
    expect(displayerForColType('integer')).toEqual({
      displayer: 'float',
      min_fraction_digits: 0,
      max_fraction_digits: 0,
    });
  });
  it('renders floats with 3 fraction digits', () => {
    expect(displayerForColType('float')).toEqual({
      displayer: 'float',
      min_fraction_digits: 3,
      max_fraction_digits: 3,
    });
  });
  it('renders datetimes with the en-US locale displayer', () => {
    expect(displayerForColType('datetime')).toEqual({
      displayer: 'datetimeLocaleString',
      locale: 'en-US',
      args: {},
    });
  });
});

describe('buildColumnConfig', () => {
  const plan = buildRenamePlan([
    { name: 'price', type: 'DOUBLE' },
    { name: 'qty', type: 'BIGINT' },
    { name: 'name', type: 'VARCHAR' },
  ] as DescribeRow[]);
  const cc = buildColumnConfig(plan);

  it('uses the alias as col_name and the original as header_name', () => {
    expect(cc[0]).toMatchObject({ col_name: 'a', header_name: 'price' });
    expect(cc[1]).toMatchObject({ col_name: 'b', header_name: 'qty' });
  });

  it('attaches a tooltip only to string columns, keyed by the alias', () => {
    expect(cc[2].tooltip_config).toEqual({ tooltip_type: 'simple', val_column: 'c' });
    expect(cc[0].tooltip_config).toBeUndefined();
  });
});

describe('buildPinnedRows / buildDfViewerConfig', () => {
  it('pins the v1 stats: dtype via obj, histogram via histogram, the rest inherit', () => {
    const pinned = buildPinnedRows();
    expect(pinned.map((p) => p.primary_key_val)).toEqual(
      V1_PINNED_STATS.map((s) => s.stat),
    );
    expect(pinned[0]).toEqual({
      primary_key_val: 'dtype',
      displayer_args: { displayer: 'obj' },
    });
    expect(pinned[1]).toEqual({
      primary_key_val: 'histogram',
      displayer_args: { displayer: 'histogram' },
    });
    expect(pinned[2].displayer_args).toEqual({ displayer: 'inherit' });
  });

  it('assembles a full viewer config with a left index column', () => {
    const plan = buildRenamePlan([{ name: 'x', type: 'INTEGER' }] as DescribeRow[]);
    const cfg = buildDfViewerConfig(plan);
    expect(cfg.column_config).toHaveLength(1);
    expect(cfg.left_col_configs[0].col_name).toBe('index');
    expect(cfg.pinned_rows.length).toBe(V1_PINNED_STATS.length);
  });
});
