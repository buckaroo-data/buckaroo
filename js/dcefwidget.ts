// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.
import _ from 'lodash';
import {
  DOMWidgetModel,
  DOMWidgetView,
  ISerializers,
  WidgetModel,
  WidgetView,
} from '@jupyter-widgets/base';

import { WidgetDCFCell } from './components/DCFCell';

import * as Backbone from 'backbone';

import React, { useEffect, useState } from 'react';
import * as ReactDOMClient from 'react-dom/client';
import { MODULE_NAME, MODULE_VERSION } from './version';

// Import the CSS
import '@ag-grid-community/styles/ag-grid.css';
import '@ag-grid-community/styles/ag-theme-alpine.css';

import '../js/style/dcf-npm.css';
import { DFViewer } from './components/DFViewerParts/DFViewer';
import { InfiniteWrapper } from './components/DFViewerParts/TableInfinite';
import { BuckarooInfiniteWidget } from './components/BuckarooWidgetInfinite';

function createModelAndView(
  model_name: string,
  widget_name: string,
  WrappedComponent: (arg0: any) => React.JSX.Element
): [typeof WidgetModel, typeof WidgetView] {
  class CustomModel extends DOMWidgetModel {
    defaults(): Backbone.ObjectHash {
      return {
        ...super.defaults(),
        _model_name: model_name,
        _model_module: CustomModel.model_module,
        _model_module_version: CustomModel.model_module_version,
        _view_name: widget_name,
        _view_module: CustomModel.view_module,
        _view_module_version: CustomModel.view_module_version,
      };
    }

    static serializers: ISerializers = {
      ...DOMWidgetModel.serializers,
    };

    static model_name = model_name;
    static model_module = MODULE_NAME;
    static model_module_version = MODULE_VERSION;
    static view_name = widget_name;
    static view_module = MODULE_NAME;
    static view_module_version = MODULE_VERSION;
  }

  class CustomView extends DOMWidgetView {
    render(): void {
      this.el.classList.add('custom-widget');

      const Component = () => {
        // this is taken from the AnyWidget implementation
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
        return React.createElement(WrappedComponent, props);
      };

      const root = ReactDOMClient.createRoot(this.el);
      const componentEl = React.createElement(Component, {});
      root.render(componentEl);
    }
  }
  return [CustomModel, CustomView];
}

export const [DCEFWidgetModel, DCEFWidgetView] = createModelAndView(
  'DCEFWidgetModel',
  'DCEFWidgetView',
  WidgetDCFCell
);

export const [BuckarooInfiniteWidgetModel, BuckarooInfiniteWidgetView] =
  createModelAndView(
    'BuckarooInfiniteWidgetModel',
    'BuckarooInfiniteWidgetView',
    BuckarooInfiniteWidget
  );

export const [InfiniteViewerModel, InfiniteViewerView] = createModelAndView(
  'InfiniteViewerModel',
  'InfiniteViewerView',
  InfiniteWrapper
);

export const [DFViewerModel, DFViewerView] = createModelAndView(
  'DFViewerModel',
  'DFViewerView',
  DFViewer
);
