import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { useState } from "react";
import srt from "buckaroo-js-core";
import "./widget.css";
import "../buckaroo-js-core/dist/style.css";



/**
 * @template {Record<string, any>} T
 * @typedef RenderContext
 * @property {import("@anywidget/types").AnyModel<T>} model
 * @property {import("@anywidget/types").Experimental} experimental
 */

/** @type {React.Context<RenderContext<any>>} */
let RenderContext = React.createContext(/** @type {any} */ (null));

/**
 * @returns {RenderContext<any>}
 */
function useRenderContext() {
	let ctx = React.useContext(RenderContext);
	if (!ctx) throw new Error("RenderContext not found");
	return ctx;
}

/**
 * @template {Record<string, any>} T
 * @returns {import("@anywidget/types").AnyModel<T>}
 */
export function useModel() {
	let ctx = useRenderContext();
	return ctx.model;
}

/** @returns {import("@anywidget/types").Experimental} */
export function useExperimental() {
	let ctx = useRenderContext();
	return ctx.experimental;
}

/**
 * A React Hook to use model-backed state in a component.
 *
 * Mirrors the API of `React.useState`, but synchronizes state with
 * the underlying model provded by an anywidget host.
 *
 * @example
 * ```ts
 * import * as React from "react";
 * import { useModelState } from "@anywidget/react";
 *
 * function Counter() {
 *   let [value, setValue] = useModelState<number>("value");
 *
 *   return (
 *     <button onClick={() => setValue((v) => v + 1)}>
 *       Count: {value}
 *     </button>
 *   );
 * }
 * ```
 *
 * @template S
 * @param {string} key - The name of the model field to use
 * @returns {[S, React.Dispatch<React.SetStateAction<S>>]}
 */
export function useModelState(key) {
	let model = useModel();
	let value = React.useSyncExternalStore(
		(update) => {
			model.on(`change:${key}`, update);
			return () => model.off(`change:${key}`, update);
		},
		() => model.get(key),
	);
	/** @type {React.Dispatch<React.SetStateAction<S>>} */
	let setValue = React.useCallback(
		(value) => {
			model.set(
				key,
				// @ts-expect-error - TS cannot correctly narrow type
				typeof value === "function" ? value(model.get(key)) : value,
			);
			model.save_changes();
		},
		[model, key],
	);
	return [value, setValue];
}

//patched version of createRender that doesn't use strict mode
// increased performance and danger
function createRender(Widget) {
	return ({ el, model, experimental }) => {
		let root = ReactDOM.createRoot(el);
		root.render(
				React.createElement(
					RenderContext.Provider,
					{ value: { model, experimental } },
					React.createElement(Widget),
				),
		);
		return () => root.unmount();
	};
}

const renderDFV = createRender(() => {
	console.log("renderDFV");
	const [df_data, _set_df_meta] = useModelState("df_data");
	const [df_viewer_config, _set_dfvc] = useModelState("df_viewer_config");
	const [summary_stats_data, _set_ssd] = useModelState("summary_stats_data");
	console.log("df_data", df_data);
	console.log("df_viewer_config", df_viewer_config);
	console.log("summary_stats_data", summary_stats_data);
	return (
		<div className="buckaroo_anywidget">
			<srt.DFViewer
				df_data={df_data}
				df_viewer_config={df_viewer_config}
				summary_stats_data={summary_stats_data}
			/>
		</div>
	);
});

const renderBuckarooWidget = createRender(() => {
	const [df_data_dict, _set_df_data_dict] = useModelState("df_data_dict");
	const [df_display_args, _set_dda] = useModelState("df_display_args");
	const [df_meta, _set_df_meta] = useModelState("df_meta");

	const [operations, on_operations] = useModelState("operations");
	const [operation_results, _set_opr] = useModelState("operation_results");
	const [command_config, _set_cc] = useModelState("command_config");

	const [buckaroo_state, on_buckaroo_state] = useModelState("buckaroo_state");
	const [buckaroo_options, _set_boptions] = useModelState("buckaroo_options");
	return (
		<div className="buckaroo_anywidget">
			<srt.WidgetDCFCell
				df_data_dict={df_data_dict}
				df_display_args={df_display_args}
				df_meta={df_meta}
				operations={operations}
				on_operations={on_operations}
				operation_results={operation_results}
				command_config={command_config}
				buckaroo_state={buckaroo_state}
				on_buckaroo_state={on_buckaroo_state}
				buckaroo_options={buckaroo_options}
			/>
		</div>
	);
});

const srcClosureRBI = (src) => {
    const renderBuckarooInfiniteWidget = createRender((a,b,c) => {
	const model = useModel()
	const [df_data_dict, _set_df_data_dict] = useModelState("df_data_dict");
	const [df_display_args, _set_dda] = useModelState("df_display_args");
	const [df_meta, _set_df_meta] = useModelState("df_meta");

	const [operations, on_operations] = useModelState("operations");
	const [operation_results, _set_opr] = useModelState("operation_results");
	const [command_config, _set_cc] = useModelState("command_config");
	const [buckaroo_state, on_buckaroo_state] = useModelState("buckaroo_state");
	const [buckaroo_options, _set_boptions] = useModelState("buckaroo_options");
	return (
	    <div className="buckaroo_anywidget">
	    <srt.BuckarooInfiniteWidget
	    
	    df_data_dict={df_data_dict}
	    df_display_args={df_display_args}
	    df_meta={df_meta}
	    operations={operations}
	    on_operations={on_operations}
	    operation_results={operation_results}
	    command_config={command_config}
	    buckaroo_state={buckaroo_state}
	    on_buckaroo_state={on_buckaroo_state}
	    buckaroo_options={buckaroo_options}
	    src={src}
		/>
		</div>
	);
    });

    const renderDFViewerInfiniteWidget = createRender((a,b,c) => {
	const model = useModel()
	const [df_meta, _set_df_meta] = useModelState("df_meta");
	const [df_data_dict, _set_df_data_dict] = useModelState("df_data_dict");
	const [df_display_args, _set_dda] = useModelState("df_display_args");
        const [df_id, _set_df_id] = useModelState("df_id");
	return (
	    <div className="buckaroo_anywidget">
		<srt.DFViewerInfiniteDS
                    df_meta={df_meta}
                    df_data_dict={df_data_dict}
                    df_display_args={df_display_args}
                    df_id={df_id}
	            src={src}
		/>
		</div>
	);
    });

    return [renderBuckarooInfiniteWidget, renderDFViewerInfiniteWidget];
}

export default async () => {
    let extraState = {};
    return {
	initialize({ model }) {
	    // we only want to create KeyAwareSmartRowCache once, it caches sourceName too
	    // so having it live between relaods is key
	    //const [respError, setRespError] = useState<string | undefined>(undefined);
	    const setRespError = (a,b) => {console.log("setRespError",a,b);}
	    extraState['keySmartCache'] = srt.getKeySmartRowCache(model, setRespError);
	    const [renderBuckarooInfinite, renderDFViewerInfinite] = srcClosureRBI(extraState['keySmartCache']);
	    extraState['renderBuckarooInfinite'] = renderBuckarooInfinite;
	    extraState['renderDFViewerInfinite'] = renderDFViewerInfinite;
	},
	render({ model, el, experimental }) {
	    const render_func_name = model.get("render_func_name");
	    if (render_func_name === "DFViewer") {
		renderDFV({ el, model, experimental });
	    } else if (render_func_name === "BuckarooWidget") {
		renderBuckarooWidget({ el, model, experimental });
	    } else if (render_func_name === "BuckarooInfiniteWidget") {
		extraState['renderBuckarooInfinite']({ el, model, experimental });
	    } else if (render_func_name === "DFViewerInfinite") {
		extraState['renderDFViewerInfinite']({ el, model, experimental });
	    }
	}
    }
}

