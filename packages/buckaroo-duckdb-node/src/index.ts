// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

export { DuckBackend } from './backend';
export type { DuckBackendOptions } from './backend';

export type {
  DuckSource,
  DescribeRow,
  SummarizeRow,
  SDType,
  SDVal,
} from './DuckSource';

export {
  buildRenamePlan,
  colAlias,
  quoteIdent,
  INDEX_COL,
} from './rename';
export type { RenamePlan } from './rename';

export {
  effectiveQuery,
  windowedQuery,
  countQuery,
} from './query';
export type { QueryTransform, WindowParams } from './query';

export { duckTypeToColType, displayerForColType } from './duckTypes';
export type { ColType } from './duckTypes';

export {
  buildColumnConfig,
  buildDfViewerConfig,
  buildPinnedRows,
  buildLeftColConfigs,
  V1_PINNED_STATS,
} from './columnConfig';

export {
  summarizeToSDType,
  sdTypeToStatRows,
  sdTypeToWideRow,
  V1_STAT_NAMES,
} from './stats';

export { IpcDuckModel, makeIpcMainHandler } from './transport';
export type { IModel, IpcInvoke } from './transport';

export type * from './wireTypes';

// The @duckdb/node-api adapter is a separate entry point so the core imports
// zero native bindings: import from 'buckaroo-duckdb-node/node-api'.
