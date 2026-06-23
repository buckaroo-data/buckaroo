// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

export { DuckBackend } from './backend.js';
export type { DuckBackendOptions } from './backend.js';

export type {
  DuckSource,
  DescribeRow,
  SummarizeRow,
  SDType,
  SDVal,
} from './DuckSource.js';

export {
  buildRenamePlan,
  colAlias,
  quoteIdent,
  INDEX_COL,
} from './rename.js';
export type { RenamePlan } from './rename.js';

export {
  effectiveQuery,
  windowedQuery,
  countQuery,
} from './query.js';
export type { QueryTransform, WindowParams } from './query.js';

export { duckTypeToColType, displayerForColType } from './duckTypes.js';
export type { ColType } from './duckTypes.js';

export {
  buildColumnConfig,
  buildDfViewerConfig,
  buildPinnedRows,
  buildLeftColConfigs,
  V1_PINNED_STATS,
} from './columnConfig.js';

export {
  summarizeToSDType,
  sdTypeToStatRows,
  sdTypeToWideRow,
  V1_STAT_NAMES,
} from './stats.js';

export { IpcDuckModel, makeIpcMainHandler } from './transport.js';
export type { IModel, IpcInvoke } from './transport.js';

export type * from './wireTypes.js';

// The @duckdb/node-api adapter is a separate entry point so the core imports
// zero native bindings: import from 'buckaroo-duckdb-node/node-api'.
