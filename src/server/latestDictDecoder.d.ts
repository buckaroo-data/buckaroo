import { DFData, DFDataOrPayload } from '../components/DFViewerParts/DFWhole';
export type RawDFDataDict = Record<string, DFDataOrPayload> | undefined | null;
/**
 * Decode df_data_dict values arriving from a model and hand `apply` only the
 * newest result.
 *
 * A full `initial_state` reaches a view twice, as `change:df_data_dict` and
 * then as `metadata`, and both handlers read the same dict off the model. The
 * returned function ignores a dict it has already seen (same reference), so
 * that frame decodes once. Decoding is async, so a slow decode of an earlier
 * dict can finish after a later one; each call takes a token, and a result is
 * applied only if no later call has started.
 *
 * `seen` is a dict the caller has already applied (the view's seed), so the
 * first read of that same dict off the model does not decode it again.
 */
export declare function makeLatestDictDecoder(apply: (decoded: Record<string, DFData>) => void, seen?: RawDFDataDict): (raw: RawDFDataDict) => void;
