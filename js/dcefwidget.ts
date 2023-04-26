// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import {
  DOMWidgetModel,
  DOMWidgetView,
  ISerializers,
} from '@jupyter-widgets/base';


import _ from 'lodash';

import {WidgetDCFCell, CommandConfigT, DFWhole, CommandConfigSetterT, Operation, DependentTabs  } from 'paddy-react-edit-list';

import { createRoot } from "react-dom/client";
import React from "react";

import { MODULE_NAME, MODULE_VERSION } from './version';

// Import the CSS

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import 'paddy-react-edit-list/css/dcf-npm.css';
import '../style/widget.css';


export class DCEFWidgetModel extends DOMWidgetModel {
    defaults() {
	return {
	    ...super.defaults(),
	    _model_name: DCEFWidgetModel.model_name,
	    _model_module: DCEFWidgetModel.model_module,
	    _model_module_version: DCEFWidgetModel.model_module_version,
	    _view_name: DCEFWidgetModel.view_name,
	    _view_module: DCEFWidgetModel.view_module,
	    _view_module_version: DCEFWidgetModel.view_module_version,
	    //add typing from OperationUtils
	    command_config: {} as CommandConfigT,
	    operations: [] as Operation[],
	    operation_results: {} // {transformed_df:DFWhole, generated_py_code:string}
	};
    }


    static serializers: ISerializers = {
	...DOMWidgetModel.serializers,
	// Add any extra serializers here
    };

    static model_name = 'DCEFWidgetModel';
    static model_module = MODULE_NAME;
    static model_module_version = MODULE_VERSION;
    static view_name = 'ExampleView'; // Set to null if no view
    static view_module = MODULE_NAME; // Set to null if no view
    static view_module_version = MODULE_VERSION;
}


export class DCEFWidgetView extends DOMWidgetView {
    render() {
	console.log('DCFWidget View... renamed ')
	this.el.classList.add('custom-widget');
	//this.value_changed();
	const root = createRoot(this.el as HTMLElement)
	
	const widgetModel = this.model
	const widget = this
	widgetModel.on(
	    'change:command_config',
	    () => {
		widget.setCommandConfig(widgetModel.get('command_config'))},
	    this)

	const widgetGetOrRequester:DependentTabs.getOperationResultSetterT = (setOpResult) => {
	    widgetModel.on('change:operation_results', () => {
	    	const opResults:DependentTabs.OperationResult = widgetModel.get('operation_results')
			console.log("about to call setOpResult with", opResults)
			setOpResult(opResults)	    
	    }, this)
	    
	    const retFunc = (passedOperations:Operation[]) => {
		console.log("orRequester passed operations", passedOperations)
		widgetModel.set('operations', passedOperations)
		widgetModel.save_changes()

	    }
	    return retFunc
	};

	const commandConfig = widgetModel.get('command_config')
	console.log("widget, commandConfig", commandConfig, widgetModel)
	const plumbCommandConfig:CommandConfigSetterT = (setter) => {
	    widget.setCommandConfig = setter
	}
	
	const reactEl = React.createElement(WidgetDCFCell, {
	    origDf:widgetModel.get('js_df'),
	    getOrRequester:widgetGetOrRequester,
	    commandConfig,
	    exposeCommandConfigSetter:plumbCommandConfig,
	}, null)
	
	root.render(reactEl);
    }

    setCommandConfig = (conf:CommandConfigT) => {
	console.log("default setCommandConfig")
    }
    setPyCode = (newPyCode:string) => {
	console.log("default setPyCode")
    }
    setTransformedDf = (newDf:DFWhole) => {
	console.log("default setTransformedDf")
    }
}

/*
console.log("144")

	const widgetGetTransformRequester = (setDf:any) => {
	    widget.setTransformedDf = (inputDf:DFWhole) => {
		const opResults = widgetModel.get('operation_results')
		const generated_py_code = opResults.generated_py_code
		console.log("setDf Wrapper being called - generated_py_code", generated_py_code)
		setDf(inputDf)
	    };
	    // widgetModel.on('change:transformed_df', () => {
	    // 	setDf(widgetModel.get('transformed_df') as DFWhole)
	    // }, this)
	    
	    const baseRequestTransform = (passedInstructions:any) => {
		console.log("transform passedInstructions", passedInstructions)
		widgetModel.set('commands', passedInstructions)
		widgetModel.save_changes()
	    };
	    return baseRequestTransform;
	};
	//_.delay(() => {widget.setPyCode("widget level getPyRequester")}, 500)
	//this onChange gets called, the one inside of widgetGetPyRequester doesn't get called

	widgetModel.on('change:operation_results', () => {
	    const opResults = widgetModel.get('operation_results')
	    console.log("operation_results", opResults)
	    widget.setPyCode(opResults.generated_py_code)
	    widget.setTransformedDf(opResults.transformed_df)
	    //widget.setPyCode("padddy")
	    //widgetModel.save_changes()
	}, this)
*/
