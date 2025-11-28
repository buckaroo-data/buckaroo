import * as _ from "lodash";
import {
    DFData,
} from "./DFWhole";


export interface RowRequest {
    start: number;
    end: number
}


export type Segment = [number, number];
export type RequestArgs = RowRequest | true;
export type SegData = [Segment, DFData];

export interface PayloadArgs {
    sourceName: string;
    start: number;
    end: number;
    origEnd:number;
    sort?: string;
    sort_direction?: string;
    request_time?:number;
    second_request?: PayloadArgs
}

export interface PayloadResponse {
    key: PayloadArgs;
    data: DFData;
    length: number;
    error_info?: string;
}


export const getPayloadKey = (payloadArgs: PayloadArgs): string => {
    return `${payloadArgs.sourceName}-${payloadArgs.start}-${payloadArgs.end}-${payloadArgs.sort}-${payloadArgs.sort_direction}`;
};

export const getSourcePayloadKey = (payloadArgs: PayloadArgs): string => {
    // exclude start and end, we need to know which cache to append to
    return `${payloadArgs.sourceName}-${payloadArgs.sort}-${payloadArgs.sort_direction}`;
};



export const mergeSegments = (segments: Segment[], dfs: DFData[], newSegment: Segment, newDF: DFData): [Segment[], DFData[]] => {


    if (segments.length == 0) {
        return [[newSegment], [newDF]]
    }
    const [newStart, newEnd] = newSegment;
    const [firstStart, _firstEnd] = segments[0];
    if (newEnd < firstStart) {
        return [[newSegment, ...segments], [newDF, ...dfs]]
    }

    const [retSegments, retDFs]: [Segment[], DFData[]] = [[], []];

    for (var i = 0; i < segments.length; i++) {
        const [seg, df] = [segments[i], dfs[i]];
        if (segmentsOverlap(seg, newSegment)) {
            const [addSegment, addDf] = merge([seg, df], [newSegment, newDF]);
            //slicing greater than the length of an array returns []
            const restSegments = retSegments.concat(segments.slice(i + 1))
            const restDfs = retDFs.concat(dfs.slice(i + 1))

            // it's possible that this could be slow if we have to
            // call recursively a bunch. I doubt it because I can't
            // think of many request patterns that leave a fragmented
            // segment set. You'll either be scrolling from one side
            // or the other. Not adding stuff in the middle which
            // causes a bunch of merging.
            return mergeSegments(restSegments, restDfs, addSegment, addDf);
        }
        retSegments.push(seg)
        retDFs.push(df)

        if (i < (segments.length - 1)) {
            if (segmentBetween(newSegment, seg, segments[i + 1])) {
                retSegments.push(newSegment);
                retDFs.push(newDF);
            }
        }
    }
    const [_lastStart, lastEnd] = segments[segments.length - 1];
    if (lastEnd < newStart) {
        retSegments.push(newSegment);
        retDFs.push(newDF);
    }
    return [retSegments, retDFs]
}

export const merge = (leftSD: SegData, rightSD: SegData): SegData => {
    // This is the core performance sensitive function

    // verify this is the fastest method
    const [leftSeg, leftDF] = leftSD;
    const [rightSeg, rightDF] = rightSD;
    if (segmentLT(rightSeg, leftSeg)) {
        // it's easier if left is always less than right
        return merge(rightSD, leftSD);
    }
    const [lStart, lEnd] = leftSeg;
    const [rStart, rEnd] = rightSeg;
    if (lStart < rStart && rEnd < lEnd) {
        // if leftSD entirely contains rightSD, just return left
        return leftSD
    }

    if (lEnd === rStart) {
        const combinedDFData = leftDF.concat(rightDF)
        return [[lStart, rEnd], combinedDFData]
    }
    const sliceEnd = rStart - lEnd;
    const combinedDFData = leftDF.slice(0, sliceEnd).concat(rightDF)
    return [[lStart, rEnd], combinedDFData]
}

export const segmentBetween = (test: Segment, segLow: Segment, segHigh: Segment): boolean => {
    if (segmentLT(segHigh, segLow)) {
        return segmentBetween(test, segHigh, segLow)
    }


    const [tStart, tEnd] = test;
    const lowEnd = segLow[1]
    const highStart = segHigh[0];
    if (lowEnd < tStart && tEnd < highStart) {
        return true
    }
    return false;
}

export const segmentLT = (a: Segment, b: Segment): boolean => {

    const [aStart, aEnd] = a;
    const [bStart, bEnd] = b;

    if (aStart < bStart) {
        return true
    } else if (aStart == bStart && aEnd < bEnd) {
        //if they start in the same place, but a ends before b
        return true
    }
    return false;
}


export const segmentSubset = (outer: Segment, inner: Segment): boolean => {

    const [oStart, oEnd] = outer;
    const [iStart, iEnd] = inner;

    if (oStart <= iStart && iEnd <= oEnd) {
        return true
    }
    return false;
}


export const segmentsOverlap = (segmentA: Segment, segmentB: Segment): boolean => {
    if (segmentLT(segmentB, segmentA)) {
        return segmentsOverlap(segmentB, segmentA)
    }
    const [aLow, aHigh] = segmentA;
    const [bLow, bHigh] = segmentB;


    if (aLow <= bHigh && aHigh >= bLow) {
        return true
    }
    return false;
}

export const segmentIntersect = (segmentA: Segment, segmentB: Segment): Segment => {
    const [aLow, aHigh] = segmentA;
    const [bLow, bHigh] = segmentB;
    return [Math.max(aLow, bLow), Math.min(aHigh, bHigh)]
}

export const minimumFillArgs = (haveSegment: Segment, needSegment: Segment): RequestArgs => {
    /* given a segment that we have in cache, and a segment we need,
       return the minimum request size to satisfy needSegment */
    const [haveLow, haveHigh] = haveSegment;
    const [needLow, needHigh] = needSegment;

    if (!segmentsOverlap(haveSegment, needSegment)) {
        return { start: needLow, end: needHigh }
    } else if (segmentSubset(haveSegment, needSegment)) {
        return true
    }
    else if (needLow === haveLow) {
        return { start: haveHigh, end: needHigh }
    }
    else if (needHigh === haveHigh) {
        return { start: needLow, end: haveLow }
    }
    else if (segmentSubset(needSegment, haveSegment)) {
        // this will duplicate the haveSegment, but we can't issue two
        // requests from here rare case not currently encountered by
        // the code, and not worth the complexity
        return { start: needLow, end: needHigh }
    }
    else if (needLow < haveLow) {
        return { start: needLow, end: haveLow }
    } else if (haveLow < needLow) {
        return { start: haveHigh, end: needHigh }
    }
    // we have none of it, so request  all of it
    return { start: needLow, end: needHigh }
}

export const getSliceRange = (haveSegment: Segment, haveDF: DFData, requestSeg: Segment): DFData => {
    const [hStart, _hEnd] = haveSegment;
    const [rStart, rEnd] = requestSeg;

    const sStart = rStart - hStart;
    const sEnd = rEnd - hStart;
    return haveDF.slice(sStart, sEnd);
}

export const getRange = (segments: Segment[], dfs: DFData[], requestSeg: Segment): DFData => {
    for (var i = 0; i < segments.length; i++) {
        const [seg, df] = [segments[i], dfs[i]];
        if (segmentSubset(seg, requestSeg)) {
            return getSliceRange(seg, df, requestSeg);
        }
    }
    throw new Error(`RequestSeg {requestSeg} not in {segments}`)
}

export const segmentsSize = (segments: Segment[]): number => {
    var accum = 0;
    for (var i = 0; i < segments.length; i++) {
        const [start, end] = segments[i];
        accum += end - start
    }
    return accum;
}

export const segmentSize = (seg:Segment):number => {
    const [start, end] = seg
    return end - start;
}

export const segmentMid = (seg:Segment): number => {
    return Math.floor(seg[0] + (segmentSize(seg)/2))
}

export const segmentEndDist = (lastSegment:Segment, extent:Segment):number => {
    const mid = segmentMid(lastSegment)
    const [eStart, eEnd] = extent;

    const [startDist, endDist] =  [(mid - eStart), (eEnd - mid)]
    if (startDist < endDist) {
        return -startDist
    }
    return endDist
}

export const slicedSegmentSize = (segments: Segment[], slice: Segment): number => {
    var accum = 0;
    for (var i = 0; i < segments.length; i++) {
        if (segmentsOverlap(segments[i], slice)) {
            const [start, end] = segmentIntersect(segments[i], slice)
            accum += end - start
        }
    }
    return accum;
}

export const segmentFromMidOffset = (midPoint: number, offset: number): Segment => {
    return [Math.floor(midPoint - offset), Math.floor(midPoint + offset)] as Segment;
}

export const sizeSlice = (midPoint: number, offset: number, segments: Segment[]): number => {
    return slicedSegmentSize(segments, segmentFromMidOffset(midPoint, offset))
}



export const compactSegments = (segments: Segment[], dfs: DFData[], keep: Segment): [Segment[], DFData[]] => {
    const [retSegments, retDFs]: [Segment[], DFData[]] = [[], []];
    //console.log("284 segments", segments)
    for (var i = 0; i < segments.length; i++) {
        const [seg, df] = [segments[i], dfs[i]];
        if (segmentSubset(keep, seg)) {
            //if this segment is entirely inside of keep, just add it to retVars
            retSegments.push(seg)
            retDFs.push(df)
        } else if (segmentsOverlap(keep, seg)) {
            // here we have to do something interesting
            if (segmentLT(keep, seg)) {
                //keepEnd must be less than seg end
                const newSeg: Segment = [seg[0], keep[1]]
                const sliceDf = getSliceRange(seg, df, newSeg)
                retSegments.push(newSeg)
                retDFs.push(sliceDf)
            } else {
                //the keep window extends beyond the end of this segment,  use the end of seg
                const newSeg: Segment = [keep[0], seg[1]]
                const sliceDf = getSliceRange(seg, df, newSeg)
                retSegments.push(newSeg)
                retDFs.push(sliceDf)
            }
        }
    }
    return [retSegments, retDFs];
}



export class SmartRowCache {

    public segments: Segment[] = []
    private dfs: DFData[] = []
    public sentLength: number = -1;
    // These tuning factors are sensitive.
    // there are other serverside and ag-grid tuning factors too.
    // those are "rowRequestSize" from ag-grid verify prop name
    // and the serverside followon payload size.
    // to be safe  maxSize should be 10* rowRequestSize
    // and followon payload size should be  1/3rd to 1/4 of maxSize

    // RRS = 40
    // maxSize = 400
    // followon = 100

    // given all of this we want some signal for "not at the end of cache, but fire off the next request anyways"

    // the idea is that the user shouldn't have to wait for a server side request.

    // also especially for sorting, that is expensive, fire off the
    // first cache filling with the min, but while that DF is still
    // sorted serverside, sned the followno request.


    public maxSize: number = 4000;
    public trimFactor: number = 0.8;  // trim down to trimFactor from maxSize
    public lastRequest: Segment = [0, 0];

    public usedSize(): number {
        return segmentsSize(this.segments);
    }

    public trimCache(): void {
        if (this.usedSize() < this.maxSize) {
            return
        }

        if (this.lastRequest[0] === 0 && this.lastRequest[1] === 0) {
            //throw new Error("trying to trim with no requests, unexpected");
            //console.log("trying to trim with no requests, unexpected")
            return
        }
        const last = this.lastRequest;

        const lastSegSize = last[1] - last[0]
        const mid = (lastSegSize / 2) + last[0];

        var filled = 0;

        var targetWindow = Math.floor(this.maxSize * this.trimFactor / 2)
        filled = sizeSlice(mid, targetWindow, this.segments);
        while (filled < this.maxSize) {
            filled = sizeSlice(mid, targetWindow, this.segments);
            targetWindow *= 2
        }
	const targetSize = Math.floor(this.maxSize * this.trimFactor)

        while (filled > targetSize) {
            targetWindow = Math.floor(.9 * targetWindow)
            filled = sizeSlice(mid, targetWindow, this.segments);
        }
    const keepSeg = segmentFromMidOffset(mid, targetWindow);
	const res = compactSegments(this.segments, this.dfs, keepSeg);
	this.segments = res[0]
	this.dfs = res[1]
        //[this.segments, this.dfs] = 
    }

    public getExtents(): Segment {
        if (this.segments.length === 0) {
            throw new Error("No Segments");
        }
        const last = this.segments[this.segments.length - 1];
        const first = this.segments[0];
        return [first[0], last[1]]
    }

    public safeGetExtents(): any {
        // used only for logging
        if (this.segments.length === 0) {
            return []
        }
        const last = this.segments[this.segments.length - 1];
        const first = this.segments[0];
        return [first[0], last[1]]
    }


    public addRows(newSegment: Segment, newDf: DFData): void {
        const newSegLength = newSegment[1] - newSegment[0]
        if (newDf.length !== newSegLength) {
            //throw new Error(`addRows called with a df smaller that newSegLenth ${newSegLength} ${newSegment} ${newDf.length}`)
            //console.log(`addRows called with a df smaller that newSegLenth ${newSegLength} ${newSegment} ${newDf.length}`)
	    if ((newSegment[0] + newDf.length) === this.sentLength) {
		const endSegment:Segment = [newSegment[0], this.sentLength];
		return this.addRows(endSegment, newDf);
	    }
	    return
        }
        const [newSegs, newDfs] = mergeSegments(this.segments, this.dfs, newSegment, newDf)
        this.segments = newSegs;
        this.dfs = newDfs;
        this.trimCache()
    }

    public hasRows(needSeg: Segment): RequestArgs {
        if(needSeg[0] === 0 && needSeg[1] === 0) {
            console.log("setting lastRequest to [0,0] in hasRows, this is unexpected")
        }
	if (this.sentLength > -1 && needSeg[1] > this.sentLength) {
	    const newSeg:Segment = [needSeg[0], this.sentLength]
	    return this.hasRows(newSeg)
	}
        this.lastRequest = needSeg;
        // debug visibility
        try {
            console.log("[SmartRowCache.hasRows] need", needSeg, "extents", this.safeGetExtents(), "lastRequest", this.lastRequest);
        } catch (_e) {}
        for (const ourSeg of this.segments) {
            if (segmentsOverlap(ourSeg, needSeg)) {
                return minimumFillArgs(ourSeg, needSeg)
            }
        }
        return minimumFillArgs([0, 0], needSeg)
    }

    public getRows(range: Segment): DFData {
        try {
            console.log("[SmartRowCache.getRows] range", range, "extents", this.safeGetExtents(), "segments", this.segments);
        } catch (_e) {}
        if (this.hasRows(range) === true) {
            if(range[0] === 0 && range[1] === 0) {
                console.log("unexpected setting lastRequest to [0,0] in getRows")
            }
            this.lastRequest = range;
            return getRange(this.segments, this.dfs, range)
        } else if (range[0] === 0 && range[1] > this.sentLength && this.sentLength !== 0) {
	    const fullSeg: Segment = [0, this.sentLength];
	    return getRange(this.segments, this.dfs, fullSeg)
	}
        console.error("[SmartRowCache.getRows] Missing rows error. range", range, "extents", this.safeGetExtents(), "segments", this.segments, "sentLength", this.sentLength);
        throw new Error(`Missing rows for {range}`)
    }
}


export type RequestFN = (pa: PayloadArgs) => void
export type FoundRowsCB = (df: DFData, length: number) => void;
export type FailCB = () => void;


function verifyResp(resp: PayloadResponse):boolean {
    debugger;
    if (resp.data.length === 0) {
        return false
    }
    return true
}



export class KeyAwareSmartRowCache {

    private srcAccesses: Map<string, SmartRowCache>
    private waitingCallbacks: Record<string, [FoundRowsCB, FailCB]>
    private reqFn: RequestFN;

    public maxSize: number = 10000;
    public trimFactor: number = 0.8;  // trim down to trimFactor from maxSize
    public lastRequest: Segment = [0, 0];
    public reUpDist:number = 300;  //threshhold for requesting next range

    public padding: number = 200;
    constructor(reqFn: RequestFN) {
        this.reqFn = reqFn;
        this.waitingCallbacks = {};
	this.srcAccesses = new Map();
    }


    public usedSize(): number {
        return _.sum(Array.from(this.srcAccesses.values()).map((x) => x.usedSize()))
    }

    public debugCacheState():void {
	_.map(
	    _.fromPairs(
		Array.from(this.srcAccesses.entries())),
	    (k, _c) => {console.log(k,  k.safeGetExtents())});
    }

    public hasRows(pa: PayloadArgs): boolean {
        // this should probably be "ensure rows"
        const srcKey = getSourcePayloadKey(pa)
        const seg: Segment = [pa.start, pa.origEnd];
	if (!this.srcAccesses.has(srcKey)) {
	    console.log("500 hasRows, returning False because couldn't find srcKey")
            return false
        }
	const src = this.srcAccesses.get(srcKey);
	if(src === undefined) {
	    throw new Error(`unexpected couldn't find SmartRowCache for ${srcKey}`);
	}

        const reqArgs = src.hasRows(seg)
        if (reqArgs === true) {
            return true
        }
	console.log("500 hasRows, returning False because src didn't have rows")
        return false
    }

    public getRows(pa: PayloadArgs): DFData {
        const srcKey = getSourcePayloadKey(pa)

        const seg: Segment = [pa.start, pa.origEnd];

	if (!this.srcAccesses.has(srcKey)) {
            throw new Error(`Missing source for ${pa}`)
        }
	let src = this.srcAccesses.get(srcKey);
	if(src === undefined) {
	    throw new Error(`unexpected couldn't find SmartRowCache for ${srcKey}`);
	}

	this.srcAccesses.delete(srcKey);
	this.srcAccesses.set(srcKey, src);

	if (src.sentLength !== 0 &&  src.sentLength < pa.end) {
	    const newSeg:Segment = [pa.start, src.sentLength];
	    //console.log("at failing point", newSeg, src.getExtents())
	    return src.getRows(newSeg);
	}
        return src.getRows(seg);
    }



    public maybeMakeLeadingRequest(pa:PayloadArgs): void {
        const reqSeg:Segment = [pa.start, pa.origEnd]
        const src = this.ensureRowCacheForPa(pa)
        const ex = src.safeGetExtents()
        if (ex[1] == src.sentLength) {
            console.log("not making extra request because already have to the end of the available data", ex, src.sentLength)
            return 
        }

        const exDist:number = segmentEndDist(reqSeg, ex);
        console.log("maybeMakeLeadingRequest", exDist, reqSeg, ex)
        if (exDist > 0  && exDist < this.reUpDist) {
            // only try to eagerly make requests when scrolling down
            // scrolling up happens when exDist is negative
            //@ts-ignore
            const reqTime = (new Date()) - 1 as number
            const followonArgs: PayloadArgs = {
                'sourceName': pa.sourceName, 'sort': pa.sort, 'sort_direction': pa.sort_direction,
                'start': ex[1], 'end': ex[1] + this.padding, 'origEnd': ex[1] + this.padding,   
                request_time:reqTime
            }
            // to help with segment garbage collection
            src.hasRows([ex[1], ex[1]+this.padding]) 
            this.reqFn(followonArgs);
        }
    }

    public getRequestRows(pa: PayloadArgs, cb: FoundRowsCB, failCb: FailCB): void {
        // this function fires off a request for the rows, and when
        // that request is filled calls cb
        const cbKey = getPayloadKey(pa)
        const src =  this.ensureRowCacheForPa(pa);
        //@ts-ignore
        const reqTime = (new Date()) - 1 as number
        pa.request_time = reqTime;
        try {
            console.log("[KeyAware.getRequestRows] pa", pa, "cbKey", cbKey, "extents", src.safeGetExtents(), "sentLength", src.sentLength);
        } catch (_e) {}
        if (this.hasRows(pa)) {
            console.log(`request for ${[pa.start, pa.origEnd, pa.end]} in cache, extents ${src.getExtents()}`)
            // Only return rows guaranteed in cache: [start, origEnd].
            // Do NOT expand to [start, sentLength] here, as sentLength is dataset size, not cache extent.
            const seg: Segment = [pa.start, pa.origEnd];
            cb(src.getRows(seg), src.sentLength);
            const cbKey = getPayloadKey(pa)
            delete this.waitingCallbacks[cbKey]
            this.maybeMakeLeadingRequest(pa)
            return;
        }
        // note here we are using the full payload key because the start and end rows matter
        this.waitingCallbacks[cbKey] = [cb, failCb];
        // fire off the request here
        this.reqFn(pa);
    }

    public ensureRowCacheForPa(pa:PayloadArgs): SmartRowCache {
        const srcKey = getSourcePayloadKey(pa)
	console.log("592 ensureRowCacheForPa", srcKey, this.srcAccesses.has(srcKey))
	if (!this.srcAccesses.has(srcKey)){
            this.srcAccesses.set(srcKey, new SmartRowCache());
        }
        const src = this.srcAccesses.get(srcKey);
	if(src === undefined) {
	    throw new Error(`unexpected couldn't find SmartRowCache for ${srcKey}`);
	}
        return src;
    }

    public addPayloadResponse(resp: PayloadResponse) {
        const seg: Segment = [resp.key.start, resp.key.end];
        if(resp.key.request_time !== undefined ) {
            //@ts-ignore
            //const now = (new Date()) - 1 as number
            //const _respTime = now - resp.key.request_time;
            //console.log(`response had ${seg[1]-seg[0]} rows took ${respTime}`)
        }

	this.trim()
        const src = this.ensureRowCacheForPa(resp.key)
        const cbKey = getPayloadKey(resp.key)
        //const preExtents = src.safeGetExtents()

	if(resp.length < resp.key.end && resp.key.start === 0) {
	    // add tests
	    const entireSeg: Segment = [0, resp.length];
            src.addRows(entireSeg, resp.data)
	} else {
            src.addRows(seg, resp.data)
	}
        //console.log(`response before ${[resp.key.start, resp.key.origEnd, resp.key.end]} before add, preExtents ${preExtents}, post extents ${src.safeGetExtents()}`)
        src.sentLength = resp.length;
        if (_.has(this.waitingCallbacks, cbKey)) {
            const [success, fail] = this.waitingCallbacks[cbKey];
            if(verifyResp(resp)) {
                success(this.getRows(resp.key), src.sentLength);
            } else {
                fail()
            }
            delete this.waitingCallbacks[cbKey]
        }
    }

    public addErrorResponse(resp: PayloadResponse) {
        const cbKey = getPayloadKey(resp.key)

        if (_.has(this.waitingCallbacks, cbKey)) {
            const [_success, fail] = this.waitingCallbacks[cbKey];
            fail()
            delete this.waitingCallbacks[cbKey]
        }
    }

    public trim(): void {

	if(this.usedSize() > this.maxSize) {
	    const lastUsedKey = this.srcAccesses.keys().next().value;
	    if (lastUsedKey !== undefined) {
		this.srcAccesses.delete(lastUsedKey)
	    } else {
	    throw new Error(`unexpected couldn't find any keys in srcAccesses `);
	    }

	    
		
	}
        /*
          trim should go through sources in least recently used order.
          and trim each of the caches to the initial display size.
    
          Then if more space is needed, start deleting the older caches.
    
         */

    }
}
