// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import {
  DOMWidgetModel,
  DOMWidgetView,
  ISerializers,
} from '@jupyter-widgets/base';


import _ from 'lodash';

import {WidgetDCFCell, CommandConfigT, DFWhole, CommandConfigSetterT, Operation, DependentTabs  } from 'paddy-react-edit-list';

//import { createRoot } from "react-dom/client";
import React, {useEffect, useState} from "react";
//import * as ReactDOM from 'react-dom';
import * as ReactDOMClient from 'react-dom/client';
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
	    dfConfig: {} // provided on df ingest
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


	// const reactEl = React.createElement(WidgetDCFCell, {
	//     origDf:widgetModel.get('js_df'),
	//     getOrRequester:widgetGetOrRequester,
	//     commandConfig,
	//   exposeCommandConfigSetter:plumbCommandConfig,
	//   dfConfig:dfConfig,
	//   on_dfConfig:on_dfConfig
	// }, null)
	// root.render(reactEl);

export class DCEFWidgetView extends DOMWidgetView {

    setCommandConfig = (conf:CommandConfigT) => console.log("default setCommandConfig")
    setPyCode = (newPyCode:string) => console.log("default setPyCode")
    setTransformedDf = (newDf:DFWhole) => console.log("default setTransformedDf")
    render() {
	console.log('DCFWidget View... renamed ')
	this.el.classList.add('custom-widget');

	
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

    // const dfConfig = {
    //     totalRows: 1309,
    //     columns: 30,
    //     rowsShown: 500,
    //     sampleSize: 10_000,
    //     summaryStats: false,
    //     reorderdColumns: false
    // };

      //const on_dfConfig = (newVal:any) => console.log("on_dfConfig called with", newVal)

      const outerProps = {
	    origDf:widgetModel.get('js_df'),
	    getOrRequester:widgetGetOrRequester,
	    commandConfig,
	  exposeCommandConfigSetter:plumbCommandConfig,
	  //dfConfig:dfConfig,
	  //on_dfConfig:on_dfConfig
      };


      const Component = () => {
      // @ts-ignore
      const [_, setCounter] = useState(0);
      const forceRerender = () => {
        setCounter((x:number) => x + 1);
      }
      useEffect(() => {
        this.listenTo(this.model, 'change', forceRerender);
      }, []);


      const props : any = {...outerProps}
      for (const key of Object.keys(this.model.attributes)) {
        props[key] = this.model.get(key);
        props["on_" + key] = (value: any) => {
          this.model.set(key, value);
          this.touch();
        };
      }
	const el = React.createElement(WidgetDCFCell, props)
	return el
      }


  const root = ReactDOMClient.createRoot(this.el);
  const componentEl = React.createElement(Component, {});
  root.render(componentEl)
    
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
