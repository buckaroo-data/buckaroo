import { RefObject } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
/**
 * Reports a widget root's natural rendered height to its host.
 *
 * The Buckaroo widget root fills its container (`height: 100%`), but its
 * content — the status bar plus the grid viewport, which is capped at
 * `component_config.dfvHeight` (default `window.innerHeight / 2`) — is usually
 * shorter than the container a host gives it. The leftover space shows as a gap
 * below the table. Hosts used to work around this by reaching into AG Grid's
 * internal DOM to measure the real height; this hook does the measuring inside
 * Buckaroo and reports it, so a host can collapse its wrapper without depending
 * on AG Grid class names.
 *
 * The natural height is the bottom of the root's lowest child relative to the
 * root's top (the root's own children are content-sized even when the root
 * fills its container). It is re-measured when a child resizes, when the DOM
 * mutates (e.g. the commands editor toggles in), and on window resize — the
 * grid's height tracks `window.innerHeight`. Shrinking the host wrapper does
 * not change the children's heights, so the measurement is stable.
 */
export declare function useReportContentHeight(ref: RefObject<HTMLElement>, onHeightChange?: (height: number) => void): void;
