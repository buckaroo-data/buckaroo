// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import {
  DOMWidgetModel,
  DOMWidgetView,
  ISerializers,
} from '@jupyter-widgets/base';

import {
  WidgetDCFCell,
  CommandConfigT,
  Operation,
} from 'paddy-react-edit-list';
import * as Backbone from 'backbone';

import React, { useEffect, useState } from 'react';
import * as ReactDOMClient from 'react-dom/client';
import { MODULE_NAME, MODULE_VERSION } from './version';

// Import the CSS

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import 'paddy-react-edit-list/css/dcf-npm.css';
import '../style/widget.css';

export class DCEFWidgetModel extends DOMWidgetModel {
  defaults(): Backbone.ObjectHash {
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
      dfConfig: {}, // provided on df ingest
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
  render(): void {
    this.el.classList.add('custom-widget');

    const Component = () => {
      const [_, setCounter] = useState(0);
      const forceRerender = () => {
        setCounter((x: number) => x + 1);
      };
      useEffect(() => {
        this.listenTo(this.model, 'change', forceRerender);
      }, []);

      const props: any = {};
      for (const key of Object.keys(this.model.attributes)) {
        props[key] = this.model.get(key);
        props['on_' + key] = (value: any) => {
          this.model.set(key, value);
          this.touch();
        };
      }
      return React.createElement(WidgetDCFCell, props);
    };
    //console.log("widget el", this.el)
    const notebookEl = document.getElementsByClassName(
      'jp-NotebookPanel-notebook'
    )[0];
    const elTop = this.el.getBoundingClientRect()['y'];
    const notebookTop = notebookEl.getBoundingClientRect()['y'];
    const scrollOffset = notebookTop - elTop + 50;
    //console.log("scrollOffset", scrollOffset);
    notebookEl.scroll(0, scrollOffset);
    const root = ReactDOMClient.createRoot(this.el);
    const componentEl = React.createElement(Component, {});
    root.render(componentEl);
  }
}
