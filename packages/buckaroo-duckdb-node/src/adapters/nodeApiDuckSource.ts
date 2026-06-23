/**
 * Batteries-included `DuckSource` over a `@duckdb/node-api` connection.
 *
 * Optional: the core package imports zero native bindings. Embedders who just
 * want a connection import this entry (`buckaroo-duckdb-node/node-api`) and pass
 * their live `DuckDBConnection`; aistudio-style hosts implement `DuckSource`
 * directly against their own connection in the Electron main process.
 *
 * Serialization is the COPY → tempfile parquet path (the only no-coercion path
 * with node-api@1.4.x: no Arrow output, no in-memory parquet). DuckDB serializes
 * every type natively; we never touch a `DuckDBValue`.
 */

import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { DescribeRow, DuckSource, SummarizeRow } from '../DuckSource';

/**
 * The slice of `@duckdb/node-api`'s `DuckDBConnection` this adapter uses.
 * Declared structurally so the core never imports the native module and the
 * adapter stays decoupled from node-api's (pre-stable) exact class.
 */
export interface DuckDBConnectionLike {
  run(sql: string): Promise<unknown>;
  runAndReadAll(sql: string): Promise<DuckDBReaderLike>;
}

export interface DuckDBReaderLike {
  getRowObjectsJson(): Array<Record<string, unknown>>;
}

export interface NodeApiDuckSourceOptions {
  /** Directory for the per-window temp parquet files. Defaults to the OS tmpdir. */
  tmpDir?: string;
}

/** Escape a single-quoted SQL string literal (for the COPY target path). */
function sqlString(s: string): string {
  return `'${s.replace(/'/g, "''")}'`;
}

export function createNodeApiDuckSource(
  connection: DuckDBConnectionLike,
  opts: NodeApiDuckSourceOptions = {},
): DuckSource {
  const baseTmp = opts.tmpDir ?? tmpdir();

  return {
    async describe(stmt: string): Promise<DescribeRow[]> {
      const reader = await connection.runAndReadAll(`DESCRIBE (${stmt})`);
      return reader.getRowObjectsJson().map((r) => ({
        name: String(r.column_name),
        type: String(r.column_type),
      }));
    },

    async summarize(stmt: string): Promise<SummarizeRow[]> {
      const reader = await connection.runAndReadAll(`SUMMARIZE (${stmt})`);
      return reader.getRowObjectsJson() as unknown as SummarizeRow[];
    },

    async copyToParquet(query: string): Promise<Uint8Array> {
      const dir = await mkdtemp(join(baseTmp, 'buckaroo-duck-'));
      const file = join(dir, `${randomUUID()}.parquet`);
      try {
        await connection.run(
          `COPY (${query}) TO ${sqlString(file)} (FORMAT PARQUET)`,
        );
        return await readFile(file);
      } finally {
        // best-effort cleanup; a leaked temp dir must not fail the request
        await rm(dir, { recursive: true, force: true }).catch(() => {});
      }
    },
  };
}
