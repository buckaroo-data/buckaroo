import * as React from "react";
import { createRender, useModelState } from "@anywidget/react";
import srt from "buckaroo-js-core";
import "./widget.css";
import "../packages/buckaroo-js-core/dist/style.css";

const realSummaryConfig = {
	pinned_rows: [
		{ primary_key_val: "dtype", displayer_args: { displayer: "obj" } },
		{
			primary_key_val: "min",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 3,
				max_fraction_digits: 3,
			},
		},
		{
			primary_key_val: "mean",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 3,
				max_fraction_digits: 3,
			},
		},
		{
			primary_key_val: "max",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 3,
				max_fraction_digits: 3,
			},
		},
		{
			primary_key_val: "unique_count",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 0,
				max_fraction_digits: 0,
			},
		},
		{
			primary_key_val: "distinct_count",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 0,
				max_fraction_digits: 0,
			},
		},
		{
			primary_key_val: "empty_count",
			displayer_args: {
				displayer: "float",
				min_fraction_digits: 0,
				max_fraction_digits: 0,
			},
		},
	],
	column_config: [
		{
			col_name: "index",
			displayer_args: { displayer: "string" },
			ag_grid_specs: { minWidth: 150, pinned: "left" },
		},
		{ col_name: "int_col", displayer_args: { displayer: "obj" } },
		{ col_name: "float_col", displayer_args: { displayer: "obj" } },
		{ col_name: "str_col", displayer_args: { displayer: "obj" } },
	],
};

const realSummaryTableData = [
	{ index: "dtype", int_col: "int64", float_col: "float64", str_col: "object" },
	{ index: "min", int_col: 1, float_col: 1.4285714286 },
	{ index: "max", int_col: 49, float_col: 41.4285714286, str_col: null },
	{ index: "mean", int_col: 24.75, float_col: 22.4714285714 },
	{ index: "unique_count", int_col: 4, float_col: 0, str_col: 0 },
	{ index: "empty_count", int_col: 0, float_col: 0, str_col: 0 },
	{ index: "distinct_count", int_col: 49, float_col: 29, str_col: 1 },
];

const ex_df_data = [
	{
		index: 0,
		int_col: 111111,
		b: 111111,
	},
	{
		index: 1,
		int_col: 77777,
		b: 555555,
	},
	{
		index: 2,
		int_col: 777777,
		b: 0,
	},
	{
		index: 3,
		int_col: 1000000,
		b: 28123,
	},
	{
		index: 4,
		int_col: 2111111,
		b: 482388,
	},
	{
		index: 5,
		int_col: 1235999,
		b: 5666,
	},
];

const renderBaked = createRender(() => {
	// used to test if the widget is properly rendering in an environment with baked data
	console.log("renderBaked");
	return (
		<div className="buckaroo_anywidget">
			<srt.DFViewer
				df_data={realSummaryTableData}
				df_viewer_config={realSummaryConfig}
				summary_stats_data={[]}
			/>
		</div>
	);
});

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
	console.log("renderBuckarooWidget");
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
const renderBuckarooInfiniteWidget = createRender(() => {
	console.log("renderInfiniteBuckarooWidget");
	const [payload_args, on_payload_args] = useModelState("payload_args");
	const [payload_response, _set_payload_response] =
		useModelState("payload_response");
	const [df_data_dict, _set_df_data_dict] = useModelState("df_data_dict");
	const [df_display_args, _set_dda] = useModelState("df_display_args");
	const [df_meta, _set_df_meta] = useModelState("df_meta");

	const [operations, on_operations] = useModelState("operations");
	const [operation_results, _set_opr] = useModelState("operation_results");
	const [command_config, _set_cc] = useModelState("command_config");
	const [buckaroo_state, on_buckaroo_state] = useModelState("buckaroo_state");
	const [buckaroo_options, _set_boptions] = useModelState("buckaroo_options");
	return (
	    <div className="buckaroo_anywidget" style={{width:"800px", height:"400px", border:"4px solid orange"}}>
			<srt.BuckarooInfiniteWidget
				payload_args={payload_args}
				on_payload_args={on_payload_args}
				payload_response={payload_response}
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

const render = ({ el, model, experimental }) => {
	console.log("model", model);
	console.log("model.widget_manager", model.widget_manager);
	// console.log(
	// 	"model.widget_manager.attributes",
	// 	model.widget_manager.attributes,
	// );

	const render_func_name = model.get("render_func_name");
	console.log("render_func_name", render_func_name);
	if (render_func_name === "DFViewer") {
		renderDFV({ el, model, experimental });
	} else if (render_func_name === "BuckarooWidget") {
		renderBuckarooWidget({ el, model, experimental });
	} else if (render_func_name === "BuckarooInfiniteWidget") {
		renderBuckarooInfiniteWidget({ el, model, experimental });
	} else {
		renderBaked({ el, model, experimental });
	}
};

export default { render };
