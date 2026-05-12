import { View } from './Views';
/**
 * Capacity-bounded LRU registry of views, keyed by viewKey().
 *
 * Uses the standard JS-Map insertion-order trick: a get/touch deletes
 * and re-inserts the entry to put it at the MRU end; eviction pops
 * the first iteration entry (LRU).
 *
 * Capacity 0 is allowed — anything added is evicted immediately.
 */
export declare class ViewRegistry {
    private readonly capacity;
    private readonly map;
    constructor(capacity: number);
    size(): number;
    has(viewKey: string): boolean;
    get(viewKey: string): View | undefined;
    add(view: View): View | undefined;
    delete(viewKey: string): void;
    keys(): string[];
}
