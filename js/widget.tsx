import * as React from "react";
import { useState } from "react";
import { createRender, useModelState, useModel } from "@anywidget/react";
import srt from "buckaroo-js-core";
import "./widget.css";
import "../packages/buckaroo-js-core/dist/style.css";

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

