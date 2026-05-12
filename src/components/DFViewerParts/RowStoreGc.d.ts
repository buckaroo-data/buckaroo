import { RowStore } from './RowStore';
import { View } from './Views';
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
export declare function gcRowStore(rowStore: RowStore, activeWindows: ActiveWindow[], padding: number, pin?: PinSpec): void;
