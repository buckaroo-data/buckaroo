/**
 * The injected connection seam.
 *
 * The core owns zero native bindings. An embedder hands in a `DuckSource`
 * bound to *their* live connection (with their attached databases, registered
 * files and temp views), because the stats/rows queries
 * (`COPY (SELECT … FROM (<stmt>))`) only resolve in that same catalog. A
 * self-owned connection would be a different database that can't see the
 * user's tables.
 *
 * A batteries-included `@duckdb/node-api` adapter ships alongside
 * (`buckaroo-duckdb-node/node-api`) for embedders who just want a connection.
 */
export interface DuckSource {
  /** `DESCRIBE (<stmt>)` → ordered (name, type) pairs, in select order. */
  describe(stmt: string): Promise<DescribeRow[]>;

  /** `SUMMARIZE (<stmt>)` → one row per column. */
  summarize(stmt: string): Promise<SummarizeRow[]>;

  /**
   * `COPY (<query>) TO '<tmpfile>' (FORMAT PARQUET)` → the file bytes.
   *
   * This is the only no-coercion serialization path with node-api@1.4.x
   * (no Arrow output, no in-memory parquet): DuckDB serializes every type
   * natively and the caller never touches a `DuckDBValue`.
   */
  copyToParquet(query: string): Promise<Uint8Array>;
}

/** One row of `DESCRIBE (<stmt>)`. DuckDB returns more columns; we use these. */
export interface DescribeRow {
  /** `column_name` */
  name: string;
  /** `column_type`, e.g. `BIGINT`, `DECIMAL(38,9)`, `VARCHAR`, `TIMESTAMP`. */
  type: string;
}

/**
 * One row of `SUMMARIZE (<stmt>)`. Field names match DuckDB's SUMMARIZE output.
 * Numeric fields arrive as strings from `getRowObjectsJson()`; the stats layer
 * keeps them verbatim (no coercion).
 */
export interface SummarizeRow {
  column_name: string;
  column_type: string;
  min: string | null;
  max: string | null;
  approx_unique: number | string | null;
  avg: string | null;
  std: string | null;
  q25: string | null;
  q50: string | null;
  q75: string | null;
  count: number | string | null;
  null_percentage: number | string | null;
}

/**
 * Summary-stats dict: `Dict[col, Dict[stat, val]]`.
 * Mirrors Python `SDType` (col_analysis.py:7-13). Serialized to the wide
 * `{col}__{stat}` parquet shape for the `layout:'wide'` envelope.
 */
export type SDVal = string | number | boolean | null | SDVal[];
export type SDType = Record<string, Record<string, SDVal>>;
