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
	    commandConfig: {} as CommandConfigT,
	    operations: [] as Operation[],
	  operation_results: {}, // {transformed_df:DFWhole, generated_py_code:string}
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

export class DCEFWidgetView extends DOMWidgetView {

    setCommandConfig = (conf:CommandConfigT) => console.log("default setCommandConfig")
    setPyCode = (newPyCode:string) => console.log("default setPyCode")
    setTransformedDf = (newDf:DFWhole) => console.log("default setTransformedDf")
    render() {
	this.el.classList.add('custom-widget');

	const widgetModel = this.model
	const widget = this
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

        // these following lines probably aren't necessary given the
        // ipyReact integration to the end of plumbCommandConfig
	widgetModel.on(
	    'change:commandConfig',
	    () => {
		widget.setCommandConfig(widgetModel.get('commandConfig'))},
	    this)

	const plumbCommandConfig:CommandConfigSetterT = (setter) => {
	    widget.setCommandConfig = setter
	}

      const outerProps = {
	//origDf:widgetModel.get('js_df'),
	getOrRequester:widgetGetOrRequester,
	exposeCommandConfigSetter:plumbCommandConfig,
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
	return React.createElement(WidgetDCFCell, props)
      }
      //console.log("widget el", this.el)
      const notebookEl = document.getElementsByClassName("jp-NotebookPanel-notebook")[0]
      const elTop = this.el.getBoundingClientRect()['y']
      const notebookTop = notebookEl.getBoundingClientRect()['y']
      const scrollOffset = (notebookTop - elTop) + 50;
      //console.log("scrollOffset", scrollOffset);
      notebookEl.scroll(0, scrollOffset)
  const root = ReactDOMClient.createRoot(this.el);
  const componentEl = React.createElement(Component, {});
  root.render(componentEl)
    }
}
