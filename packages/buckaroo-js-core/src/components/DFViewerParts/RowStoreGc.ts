import { RowStore } from "./RowStore";
import { View } from "./Views";


export interface ActiveWindow {
    view: View;
    start: number;
    end: number;
}


export interface PinSpec {
    views: View[];
    headSize: number;
    tailSize: number;
}


/**
 * Visibility-aware GC. For each active window, expand the position
 * range by `padding`, map through the window's view to get rowids,
 * union the lot. If `pin` is provided, also union in the first
 * `headSize` and last `tailSize` rowids of every pinned view.
 * Everything else is dropped.
 *
 * Empty active-window list + no pin spec drops everything.
 */
export function gcRowStore(
    rowStore: RowStore,
    activeWindows: ActiveWindow[],
    padding: number,
    pin?: PinSpec,
): void {
    const keep = new Set<number>();

    for (const w of activeWindows) {
        const start = Math.max(0, w.start - padding);
        const end = Math.min(w.view.length(), w.end + padding);
        if (start >= end) continue;
        for (const r of w.view.rowidsInRange(start, end)) keep.add(r);
    }

    if (pin !== undefined) {
        for (const v of pin.views) {
            const len = v.length();
            if (pin.headSize > 0) {
                const headEnd = Math.min(pin.headSize, len);
                for (const r of v.rowidsInRange(0, headEnd)) keep.add(r);
            }
            if (pin.tailSize > 0) {
                const tailStart = Math.max(0, len - pin.tailSize);
                for (const r of v.rowidsInRange(tailStart, len)) keep.add(r);
            }
        }
    }

    // Array.from rather than for-of on the iterator — the latter compiles
    // to a no-op iteration under this repo's tsconfig target.
    const allRowids = Array.from(rowStore.rowids());
    for (const rowid of allRowids) {
        if (!keep.has(rowid)) rowStore.delete(rowid);
    }
}
