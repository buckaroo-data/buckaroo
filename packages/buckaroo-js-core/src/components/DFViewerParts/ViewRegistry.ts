import { View } from "./Views";


/**
 * Capacity-bounded LRU registry of views, keyed by viewKey().
 *
 * Uses the standard JS-Map insertion-order trick: a get/touch deletes
 * and re-inserts the entry to put it at the MRU end; eviction pops
 * the first iteration entry (LRU).
 *
 * Capacity 0 is allowed — anything added is evicted immediately.
 */
export class ViewRegistry {
    private readonly capacity: number;
    private readonly map: Map<string, View> = new Map();

    constructor(capacity: number) {
        this.capacity = capacity;
    }

    public size(): number {
        return this.map.size;
    }

    public has(viewKey: string): boolean {
        return this.map.has(viewKey);
    }

    public get(viewKey: string): View | undefined {
        const v = this.map.get(viewKey);
        if (v === undefined) return undefined;
        // touch: move to MRU end
        this.map.delete(viewKey);
        this.map.set(viewKey, v);
        return v;
    }

    public add(view: View): View | undefined {
        const key = view.viewKey();
        // Re-add behaves as touch + replace
        if (this.map.has(key)) {
            this.map.delete(key);
        }
        this.map.set(key, view);
        if (this.map.size > this.capacity) {
            const lruKey = Array.from(this.map.keys())[0];
            const evicted = this.map.get(lruKey);
            this.map.delete(lruKey);
            return evicted;
        }
        return undefined;
    }

    public delete(viewKey: string): void {
        this.map.delete(viewKey);
    }

    public keys(): string[] {
        return Array.from(this.map.keys());
    }
}
