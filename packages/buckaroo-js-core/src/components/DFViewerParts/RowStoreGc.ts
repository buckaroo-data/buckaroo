import { RowStore } from "./RowStore";
import { View } from "./Views";


export interface ActiveWindow {
    view: View;
    start: number;
    end: number;
}


/**
 * Visibility-aware GC. For each active window, expand the position
 * range by `padding`, map through the window's view to get rowids,
 * union the lot, and drop everything else from the RowStore.
 *
 * Empty active-window list drops everything.
 */
export function gcRowStore(
    rowStore: RowStore,
    activeWindows: ActiveWindow[],
    padding: number,
): void {
    const keep = new Set<number>();
    for (const w of activeWindows) {
        const start = Math.max(0, w.start - padding);
        const end = Math.min(w.view.length(), w.end + padding);
        if (start >= end) continue;
        for (const r of w.view.rowidsInRange(start, end)) keep.add(r);
    }

    // Array.from rather than for-of on the iterator — the latter compiles
    // to a no-op iteration under this repo's tsconfig target.
    const allRowids = Array.from(rowStore.rowids());
    for (const rowid of allRowids) {
        if (!keep.has(rowid)) rowStore.delete(rowid);
    }
}
