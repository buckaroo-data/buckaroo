import * as React from "react";

import { BuckarooInfiniteWidget, DFViewerInfiniteDS, getKeySmartRowCache } from "../components/BuckarooWidgetInfinite";
import { preResolveDFDataDict } from "../components/DFViewerParts/resolveDFData";
import { DFMeta, BuckarooState, BuckarooOptions } from "../components/WidgetTypes";
import { CommandConfigT } from "../components/CommandUtils";
import { Operation } from "../components/OperationUtils";
import { OperationResult, baseOperationResults } from "../components/DependentTabs";
import { DFData, DFDataOrPayload } from "../components/DFViewerParts/DFWhole";
import { IDisplayArgs } from "../components/DFViewerParts/gridUtils";
import { IModel } from "./IModel";

export type BuckarooServerMode = "viewer" | "buckaroo";

export interface BuckarooServerMetadata {
    path?: string;
    rows?: number;
    [k: string]: unknown;
}

const DEFAULT_DF_META: DFMeta = { total_rows: 0, columns: 0, filtered_rows: 0, rows_shown: 0 };
const DEFAULT_BUCKAROO_STATE: BuckarooState = {
    sampled: false,
    cleaning_method: false,
    quick_command_args: {},
    post_processing: false,
    df_display: "main",
    show_commands: false,
};
const DEFAULT_BUCKAROO_OPTIONS: BuckarooOptions = {
    sampled: [],
    cleaning_method: [],
    post_processing: [],
    df_display: [],
    show_commands: [],
};
const DEFAULT_COMMAND_CONFIG: CommandConfigT = { argspecs: {}, defaultArgs: {} };

// Inline check — mirrors the (module-private) guard in resolveDFData.ts.
// We can't import it directly without widening that module's API surface.
function hasUnresolvedParquet(dict: unknown): boolean {
    if (!dict || typeof dict !== "object") return false;
    for (const v of Object.values(dict as Record<string, unknown>)) {
        if (
            v !== null &&
            typeof v === "object" &&
            !Array.isArray(v) &&
            (v as any).format === "parquet_b64" &&
            typeof (v as any).data === "string"
        ) {
            return true;
        }
    }
    return false;
}

export interface BuckarooViewProps {
    /** An already-connected model implementing {@link IModel}. The caller is
     *  responsible for transport setup (WebSocket, Tauri IPC, etc.) and for
     *  having received `initial_state` from the backend before mounting. */
    model: IModel;

    /** The first `initial_state` payload the model produced. Used to seed
     *  React state without waiting for `change:*` events. If `df_data_dict`
     *  contains base64-encoded parquet payloads they will be resolved on
     *  mount; pre-resolved values pass through unchanged. */
    initialState: Record<string, unknown>;

    /** Which widget to render — `"viewer"` for `DFViewerInfiniteDS`,
     *  `"buckaroo"` for the full `BuckarooInfiniteWidget`. */
    mode: BuckarooServerMode;

    /** Called when the backend pushes a `metadata` event (e.g. a new file
     *  was loaded). Useful for host apps that mirror the filename into a
     *  title bar. */
    onMetadata?: (metadata: BuckarooServerMetadata, prompt?: string) => void;

    /** Optional inline style applied to the wrapping div. The component
     *  defaults to `width:100%, height:100%`. */
    style?: React.CSSProperties;

    /** Optional className on the wrapping div. */
    className?: string;

    /** When true, render with AG Grid's `domLayout: "autoHeight"`: the grid
     *  grows to fit its row count instead of filling the parent container.
     *  Use for stacked-cell hosts (notebook-style embeds) where a fixed
     *  embed height looks wrong for both small and large dataframes. */
    autoHeight?: boolean;
}

export function pickMode(rawMode: unknown): BuckarooServerMode {
    if (rawMode === "buckaroo" || rawMode === "viewer") return rawMode;
    if (rawMode !== undefined && rawMode !== null) {
        console.warn(`[BuckarooView] unknown mode ${JSON.stringify(rawMode)} — falling back to "viewer".`);
    }
    return "viewer";
}

/**
 * BuckarooView — transport-agnostic Buckaroo widget renderer.
 *
 * Takes an already-connected {@link IModel} plus the `initial_state` payload
 * it produced, and renders the appropriate widget. Use this when the caller
 * owns transport setup and wants to keep WebSockets out of the renderer
 * (e.g. Tauri/Electron hosts relaying through IPC). For the common case
 * where you just want a WebSocket connection from the React tree, use
 * {@link BuckarooServerView}, which is a thin wrapper around this component.
 */
export function BuckarooView({
    model,
    initialState,
    mode,
    onMetadata,
    style,
    className,
    autoHeight,
}: BuckarooViewProps): React.ReactElement {
    // If the caller passed raw initial_state straight off the wire,
    // df_data_dict may still contain parquet_b64 payload objects. Those
    // would crash makeStaticInfiniteDs (data.slice on a payload object),
    // so block the widget render until the async resolution effect has
    // populated dfDataDict. The BuckarooServerView wrapper pre-resolves
    // before mounting, so it skips this path.
    const initialNeedsResolution = React.useMemo(
        () => hasUnresolvedParquet(initialState.df_data_dict),
        [initialState],
    );

    const [dfMeta, setDfMeta] = React.useState<DFMeta>(
        (initialState.df_meta as DFMeta) ?? DEFAULT_DF_META,
    );
    const [dfDataDict, setDfDataDict] = React.useState<Record<string, DFData>>(
        initialNeedsResolution
            ? {}
            : ((initialState.df_data_dict as Record<string, DFData>) ?? {}),
    );
    const [dataReady, setDataReady] = React.useState<boolean>(!initialNeedsResolution);
    const [dfDisplayArgs, setDfDisplayArgs] = React.useState<Record<string, IDisplayArgs>>(
        (initialState.df_display_args as Record<string, IDisplayArgs>) ?? {},
    );
    const [buckarooState, setBuckarooStateLocal] = React.useState<BuckarooState>(
        (initialState.buckaroo_state as BuckarooState) ?? DEFAULT_BUCKAROO_STATE,
    );
    const [buckarooOptions, setBuckarooOptions] = React.useState<BuckarooOptions>(
        (initialState.buckaroo_options as BuckarooOptions) ?? DEFAULT_BUCKAROO_OPTIONS,
    );
    const [commandConfig, setCommandConfig] = React.useState<CommandConfigT>(
        (initialState.command_config as CommandConfigT) ?? DEFAULT_COMMAND_CONFIG,
    );
    const [operationResults, setOperationResults] = React.useState<OperationResult>(
        (initialState.operation_results as OperationResult) ?? baseOperationResults,
    );
    const [operations, setOperations] = React.useState<Operation[]>(
        (initialState.operations as Operation[]) ?? [],
    );

    const onMetadataRef = React.useRef(onMetadata);
    React.useEffect(() => { onMetadataRef.current = onMetadata; }, [onMetadata]);

    // Resolve any parquet-encoded payloads in df_data_dict. Pre-resolved
    // dicts (e.g. when BuckarooServerView already ran preResolveDFDataDict)
    // pass through unchanged, so this is cheap in the common case. Skip
    // entirely when no resolution is needed — avoids a spurious re-render
    // for the BuckarooServerView path.
    React.useEffect(() => {
        if (!initialNeedsResolution) return;
        let cancelled = false;
        const dict = initialState.df_data_dict as Record<string, DFDataOrPayload> | undefined;
        if (!dict) {
            setDataReady(true);
            return;
        }
        preResolveDFDataDict(dict).then((d) => {
            if (cancelled) return;
            setDfDataDict(d as Record<string, DFData>);
            setDataReady(true);
        });
        return () => { cancelled = true; };
    }, [initialState, initialNeedsResolution]);

    // Fire onMetadata for the initial payload, matching BuckarooServerView's
    // pre-split behavior.
    React.useEffect(() => {
        if (initialState.metadata) {
            onMetadataRef.current?.(
                initialState.metadata as BuckarooServerMetadata,
                initialState.prompt as string | undefined,
            );
        }
    }, [initialState]);

    const src = React.useMemo(
        () => getKeySmartRowCache(model, (a: unknown, b: unknown) => console.error("[BuckarooView] cache error:", a, b)),
        [model],
    );

    React.useEffect(() => {
        const onMeta = (metadata: BuckarooServerMetadata, prompt?: string) => {
            onMetadataRef.current?.(metadata, prompt);
            setDfMeta((model.get("df_meta") as DFMeta | undefined) ?? { ...DEFAULT_DF_META, total_rows: metadata?.rows ?? 0 });
            preResolveDFDataDict((model.get("df_data_dict") as Record<string, DFDataOrPayload> | undefined) ?? {})
                .then((d) => setDfDataDict(d as Record<string, DFData>));
            setDfDisplayArgs((model.get("df_display_args") as Record<string, IDisplayArgs> | undefined) ?? {});
            setBuckarooStateLocal((model.get("buckaroo_state") as BuckarooState | undefined) ?? DEFAULT_BUCKAROO_STATE);
            setBuckarooOptions((model.get("buckaroo_options") as BuckarooOptions | undefined) ?? DEFAULT_BUCKAROO_OPTIONS);
            setCommandConfig((model.get("command_config") as CommandConfigT | undefined) ?? DEFAULT_COMMAND_CONFIG);
            setOperationResults((model.get("operation_results") as OperationResult | undefined) ?? baseOperationResults);
            setOperations((model.get("operations") as Operation[] | undefined) ?? []);
        };
        const onDfMeta = (v: DFMeta) => setDfMeta(v);
        const onDfDataDict = (v: Record<string, DFDataOrPayload>) => {
            preResolveDFDataDict(v).then((d) => setDfDataDict(d as Record<string, DFData>));
        };
        const onDfDisplayArgs = (v: Record<string, IDisplayArgs>) => setDfDisplayArgs(v);
        const onBState = (v: BuckarooState) => setBuckarooStateLocal(v);
        const onBOpts = (v: BuckarooOptions) => setBuckarooOptions(v);
        const onCmdCfg = (v: CommandConfigT) => setCommandConfig(v);
        const onOpRes = (v: OperationResult) => setOperationResults(v);
        const onOps = (v: Operation[]) => setOperations(v);

        model.on("metadata", onMeta);
        model.on("change:df_meta", onDfMeta);
        model.on("change:df_data_dict", onDfDataDict);
        model.on("change:df_display_args", onDfDisplayArgs);
        model.on("change:buckaroo_state", onBState);
        model.on("change:buckaroo_options", onBOpts);
        model.on("change:command_config", onCmdCfg);
        model.on("change:operation_results", onOpRes);
        model.on("change:operations", onOps);

        return () => {
            model.off("metadata", onMeta);
            model.off("change:df_meta", onDfMeta);
            model.off("change:df_data_dict", onDfDataDict);
            model.off("change:df_display_args", onDfDisplayArgs);
            model.off("change:buckaroo_state", onBState);
            model.off("change:buckaroo_options", onBOpts);
            model.off("change:command_config", onCmdCfg);
            model.off("change:operation_results", onOpRes);
            model.off("change:operations", onOps);
        };
    }, [model]);

    const onBuckarooState = React.useCallback<React.Dispatch<React.SetStateAction<BuckarooState>>>((newState) => {
        const resolved = typeof newState === "function"
            ? (newState as (prev: BuckarooState) => BuckarooState)(buckarooState)
            : newState;
        model.set("buckaroo_state", resolved);
        model.save_changes();
    }, [model, buckarooState]);

    const onOperations = React.useCallback((newOps: Operation[]) => {
        model.set("operations", newOps);
        model.save_changes();
    }, [model]);

    // When autoHeight is requested, force AG Grid into domLayout:"autoHeight"
    // by stamping layoutType onto each display-arg entry's component_config,
    // and drop the wrapper's height:100% so the grid can size to its rows
    // instead of being capped by the parent. The map is memoized to keep
    // child reference identity stable across re-renders.
    const effectiveDisplayArgs = React.useMemo<Record<string, IDisplayArgs>>(() => {
        if (!autoHeight) return dfDisplayArgs;
        const out: Record<string, IDisplayArgs> = {};
        for (const [k, v] of Object.entries(dfDisplayArgs)) {
            out[k] = {
                ...v,
                df_viewer_config: {
                    ...v.df_viewer_config,
                    component_config: {
                        ...(v.df_viewer_config.component_config ?? {}),
                        layoutType: "autoHeight",
                    },
                },
            };
        }
        return out;
    }, [dfDisplayArgs, autoHeight]);

    const wrapperStyle: React.CSSProperties = autoHeight
        ? { width: "100%", ...(style ?? {}) }
        : { width: "100%", height: "100%", ...(style ?? {}) };

    if (!effectiveDisplayArgs?.main || !dataReady) {
        return (
            <div className={className} style={wrapperStyle}>
                <div style={{ padding: 20, fontFamily: "sans-serif" }}>Preparing…</div>
            </div>
        );
    }

    return (
        <div className={["buckaroo_anywidget", className].filter(Boolean).join(" ")} style={wrapperStyle}>
            {mode === "buckaroo" ? (
                <BuckarooInfiniteWidget
                    df_meta={dfMeta}
                    df_data_dict={dfDataDict}
                    df_display_args={effectiveDisplayArgs}
                    operations={operations}
                    on_operations={onOperations}
                    operation_results={operationResults}
                    command_config={commandConfig}
                    buckaroo_state={buckarooState}
                    on_buckaroo_state={onBuckarooState}
                    buckaroo_options={buckarooOptions}
                    src={src}
                />
            ) : (
                <DFViewerInfiniteDS
                    df_meta={dfMeta}
                    df_data_dict={dfDataDict}
                    df_display_args={effectiveDisplayArgs}
                    src={src}
                    df_id={"server"}
                />
            )}
        </div>
    );
}
