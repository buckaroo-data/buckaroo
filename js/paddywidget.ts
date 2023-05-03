// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import {
  DOMWidgetModel,
  DOMWidgetView,
  ISerializers,
} from '@jupyter-widgets/base';

import { MODULE_NAME, MODULE_VERSION } from './version';

import { createRoot } from 'react-dom/client';
import React from 'react';

function ExampleComponent(props: any) {
  return React.createElement('h1', null, `Hello ${props.name}`);
}

console.log('paddy model module level');

//export const localModuleName = "PaddyModule"
export class PaddyModel extends DOMWidgetModel {
  defaults() {
    return {
      ...super.defaults(),
      _model_name: PaddyModel.model_name,
      _model_module: PaddyModel.model_module,
      _model_module_version: PaddyModel.model_module_version,
      _view_name: PaddyModel.view_name,
      _view_module: PaddyModel.view_module,
      _view_module_version: PaddyModel.view_module_version,
      value: 'Paddy Model',
    };
  }

  static serializers: ISerializers = {
    ...DOMWidgetModel.serializers,
    // Add any extra serializers here
  };

  static model_name = 'PaddyModel';
  static model_module = MODULE_NAME; //localModuleName
  static model_module_version = MODULE_VERSION;
  static view_name = 'PaddyView'; // Set to null if no view
  static view_module = MODULE_NAME; // Set to null if no view
  static view_module_version = MODULE_VERSION;
}

export class PaddyView extends DOMWidgetView {
  render() {
    console.log('paddy 5555735');
    this.el.classList.add('custom-widget');
    this.value_changed();
    try {
      const root = createRoot(this.el as HTMLElement);
      root.render(
        React.createElement(ExampleComponent, { name: 'Paddy' }, null)
      );
      console.log('react calls worked fine');
    } catch (e) {
      console.log('error instatiating React components', e);
    }
    this.model.on('change:value', this.value_changed, this);
  }

  value_changed() {
    //this.el.textContent = this.model.get('value') + "from_Paddy view render";
  }
}
