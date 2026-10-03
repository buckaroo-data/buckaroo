import { DFData } from './DFWhole';
export interface RowRequest {
    start: number;
    end: number;
}
export type Segment = [number, number];
export type RequestArgs = RowRequest | true;
export type SegData = [Segment, DFData];
export interface PayloadArgs {
    sourceName: string;
    start: number;
    end: number;
    origEnd: number;
    sort?: string;
    sort_direction?: string;
    request_time?: number;
    second_request?: PayloadArgs;
}
export interface PayloadResponse {
    key: PayloadArgs;
    data: DFData;
    length: number;
    error_info?: string;
}
export declare const getPayloadKey: (payloadArgs: PayloadArgs) => string;
export declare const getSourcePayloadKey: (payloadArgs: PayloadArgs) => string;
export declare const mergeSegments: (segments: Segment[], dfs: DFData[], newSegment: Segment, newDF: DFData) => [Segment[], DFData[]];
export declare const merge: (leftSD: SegData, rightSD: SegData) => SegData;
export declare const segmentBetween: (test: Segment, segLow: Segment, segHigh: Segment) => boolean;
export declare const segmentLT: (a: Segment, b: Segment) => boolean;
export declare const segmentSubset: (outer: Segment, inner: Segment) => boolean;
export declare const segmentsOverlap: (segmentA: Segment, segmentB: Segment) => boolean;
export declare const segmentIntersect: (segmentA: Segment, segmentB: Segment) => Segment;
export declare const minimumFillArgs: (haveSegment: Segment, needSegment: Segment) => RequestArgs;
export declare const getSliceRange: (haveSegment: Segment, haveDF: DFData, requestSeg: Segment) => DFData;
export declare const getRange: (segments: Segment[], dfs: DFData[], requestSeg: Segment) => DFData;
export declare const segmentsSize: (segments: Segment[]) => number;
export declare const segmentSize: (seg: Segment) => number;
export declare const segmentMid: (seg: Segment) => number;
export declare const segmentEndDist: (lastSegment: Segment, extent: Segment) => number;
export declare const slicedSegmentSize: (segments: Segment[], slice: Segment) => number;
export declare const segmentFromMidOffset: (midPoint: number, offset: number) => Segment;
export declare const sizeSlice: (midPoint: number, offset: number, segments: Segment[]) => number;
export declare const compactSegments: (segments: Segment[], dfs: DFData[], keep: Segment) => [Segment[], DFData[]];
export declare class SmartRowCache {
    segments: Segment[];
    private dfs;
    sentLength: number;
    maxSize: number;
    trimFactor: number;
    lastRequest: Segment;
    usedSize(): number;
    trimCache(): void;
    getExtents(): Segment;
    safeGetExtents(): any;
    addRows(newSegment: Segment, newDf: DFData): void;
    hasRows(needSeg: Segment): RequestArgs;
    getRows(range: Segment): DFData;
}
export type RequestFN = (pa: PayloadArgs) => void;
export type FoundRowsCB = (df: DFData, length: number) => void;
export type FailCB = () => void;
export declare class KeyAwareSmartRowCache {
    private srcAccesses;
    private waitingCallbacks;
    private reqFn;
    maxSize: number;
    trimFactor: number;
    lastRequest: Segment;
    reUpDist: number;
    padding: number;
    constructor(reqFn: RequestFN);
    usedSize(): number;
    debugCacheState(): void;
    hasRows(pa: PayloadArgs): boolean;
    getRows(pa: PayloadArgs): DFData;
    maybeMakeLeadingRequest(pa: PayloadArgs): void;
    getRequestRows(pa: PayloadArgs, cb: FoundRowsCB, failCb: FailCB): void;
    ensureRowCacheForPa(pa: PayloadArgs): SmartRowCache;
    addPayloadResponse(resp: PayloadResponse): void;
    addErrorResponse(resp: PayloadResponse): void;
    trim(): void;
}
