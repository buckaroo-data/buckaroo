/**
 * DuckDB type string → buckaroo column category → displayer args.
 *
 * The category mapping follows the plan's type map:
 *   INT / BIGINT / etc -> integer, DOUBLE / REAL / DECIMAL -> float,
 *   VARCHAR -> string, BOOLEAN -> string, DATE / TIMESTAMP / TIME -> datetime,
 *   everything else -> obj.
 *
 * The displayer *args* mirror `DefaultMainStyling.style_column`
 * (customizations/styling.py:70-142) so a column renders identically to the
 * pandas/polars backends — notably buckaroo renders integers through the
 * `float` displayer with zero fraction digits, not the `integer` displayer.
 */

import type { DisplayerArgs } from './wireTypes';

export type ColType = 'integer' | 'float' | 'datetime' | 'string' | 'obj';

/** Strip the parameter list: `DECIMAL(38,9)` → `DECIMAL`. */
function baseType(duckType: string): string {
  return duckType
    .trim()
    .toUpperCase()
    .replace(/\(.*$/, '')
    .trim();
}

const INTEGER_TYPES = new Set([
  'TINYINT',
  'SMALLINT',
  'INTEGER',
  'BIGINT',
  'HUGEINT',
  'UTINYINT',
  'USMALLINT',
  'UINTEGER',
  'UBIGINT',
  'UHUGEINT',
  'INT',
  'INT1',
  'INT2',
  'INT4',
  'INT8',
]);

const FLOAT_TYPES = new Set(['DOUBLE', 'REAL', 'FLOAT', 'FLOAT4', 'FLOAT8', 'DECIMAL', 'NUMERIC']);

export function duckTypeToColType(duckType: string): ColType {
  // Array / nested types render as object cells, not scalars.
  if (/[\[\]]/.test(duckType)) return 'obj';
  const t = baseType(duckType);
  if (t === 'STRUCT' || t === 'MAP' || t === 'LIST' || t === 'UNION') return 'obj';
  if (INTEGER_TYPES.has(t)) return 'integer';
  if (FLOAT_TYPES.has(t)) return 'float';
  if (t === 'VARCHAR' || t === 'CHAR' || t === 'TEXT' || t === 'STRING' || t === 'UUID')
    return 'string';
  if (t === 'BOOLEAN' || t === 'BOOL') return 'string'; // plan: BOOLEAN → string
  if (t === 'DATE' || t === 'TIME' || t.startsWith('TIMESTAMP')) return 'datetime';
  return 'obj';
}

/** The displayer args for a column category (DefaultMainStyling parity). */
export function displayerForColType(colType: ColType): DisplayerArgs {
  switch (colType) {
    case 'integer':
      return { displayer: 'float', min_fraction_digits: 0, max_fraction_digits: 0 };
    case 'float':
      return { displayer: 'float', min_fraction_digits: 3, max_fraction_digits: 3 };
    case 'datetime':
      return { displayer: 'datetimeLocaleString', locale: 'en-US', args: {} };
    case 'string':
      return { displayer: 'string', max_length: 35 };
    case 'obj':
      return { displayer: 'obj' };
  }
}
