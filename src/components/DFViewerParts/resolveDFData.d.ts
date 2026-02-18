import { DFData, DFDataOrPayload } from './DFWhole';
/**
 * Synchronously resolve a DFDataOrPayload to DFData.
 *
 * - If the input is already a plain DFData array, return it as-is.
 * - If it is a parquet-b64 payload, decode and parse the parquet into DFData.
 * - Falls back to an empty array on errors.
 *
 * hyparquet's parquetRead with onComplete fires synchronously when given an
 * in-memory ArrayBuffer, so this function is synchronous.
 */
export declare function resolveDFData(val: DFDataOrPayload | undefined | null): DFData;
