import { default as React } from '../../../node_modules/.pnpm/react@18.3.1/node_modules/react';
import { DFMeta, DFMetaStats, BuckarooOptions, BuckarooState } from './WidgetTypes';
import { CustomCellEditorProps } from 'ag-grid-react';
import { ThemeConfig } from './DFViewerParts/gridUtils';
export type setColumFunc = (newCol: string) => void;
export declare const fakeSearchCell: (_params: any) => import("react/jsx-runtime").JSX.Element;
export declare const SearchEditor: React.MemoExoticComponent<({ value, onValueChange, stopEditing }: CustomCellEditorProps) => import("react/jsx-runtime").JSX.Element>;
/**
 * Where the summary stats stand, as the server reports it in df_meta.stats:
 * loading while they are pending, a control to ask for them while they are not
 * computed, the reason when they failed. The cell always renders one line in a
 * fixed-width column, so changing status moves nothing.
 *
 * A session that is not computed offers the control unless the server's ceiling
 * refused the stats or nothing is left to ask for. The control's label reads
 * Continue when a run was paused on cost. It calls the host's callback with no
 * arguments; the host asks for the tier df_meta.stats allows (see forceStats).
 *
 * Once a run has reached a tier (see tierReached) the cell says which tier is on
 * screen. The control, if a tier is left, then names the next one; when none is
 * left, or there is no handler, a label says the stats are computed, whatever
 * the ceiling says, since the stats on screen are not unavailable.
 */
export declare const StatsStatusCell: (params: {
    value?: DFMetaStats;
    context?: {
        onComputeStats?: (opts?: {
            columns?: string[];
        }) => void;
    };
}) => import("react/jsx-runtime").JSX.Element | null;
export declare function StatusBar({ dfMeta, buckarooState, setBuckarooState, buckarooOptions, heightOverride, themeConfig, inFlight, componentConfig, onComputeStats, }: {
    dfMeta: DFMeta;
    buckarooState: BuckarooState;
    setBuckarooState: React.Dispatch<React.SetStateAction<BuckarooState>>;
    buckarooOptions: BuckarooOptions;
    heightOverride?: number;
    themeConfig?: ThemeConfig;
    inFlight?: boolean;
    /** Opaque component_config blob from Python. Passed into the AG-Grid
     *  context so any cell renderer can read config keys without additional
     *  prop threading. New config keys (e.g. searchDebounceMs) are added to
     *  Python's ComponentConfig TypedDict; cell renderers read them via
     *  params.context.componentConfig. */
    componentConfig?: Record<string, unknown>;
    /** Sends a forced stats_request. The stats column shows it as a button while
     *  df_meta.stats.status is "not_computed"; without it there is no button. */
    onComputeStats?: (opts?: {
        columns?: string[];
    }) => void;
}): import("react/jsx-runtime").JSX.Element;
