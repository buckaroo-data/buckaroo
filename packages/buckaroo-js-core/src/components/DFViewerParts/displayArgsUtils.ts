import type { IDisplayArgs } from "./gridUtils";

// When autoHeight is undefined the server value is left intact.
// true → "autoHeight", false → "normal" (overrides server).
export function stampLayoutType(
    args: Record<string, IDisplayArgs>,
    autoHeight: boolean | undefined,
): Record<string, IDisplayArgs> {
    if (autoHeight === undefined) return args;
    const layoutType = autoHeight ? "autoHeight" : "normal";
    const out: Record<string, IDisplayArgs> = {};
    for (const [k, v] of Object.entries(args)) {
        out[k] = {
            ...v,
            df_viewer_config: {
                ...v.df_viewer_config,
                component_config: {
                    ...(v.df_viewer_config.component_config ?? {}),
                    layoutType,
                },
            },
        };
    }
    return out;
}
