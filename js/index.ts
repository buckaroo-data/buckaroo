// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import { ColumnsEditor } from './components/ColumnsEditor';
import { DFViewer } from './components/DFViewerParts/DFViewer';
import {
  DFViewerInfinite,
  StaticWrapDFViewerInfinite,
} from './components/DFViewerParts/DFViewerInfinite';

import { WidgetDCFCell } from './components/DCFCell';
import { BuckarooInfiniteWidget } from './components/BuckarooWidgetInfinite';

import { HistogramCell } from './components/DFViewerParts/HistogramCell';
import { InfiniteEx } from './components/DFViewerParts/TableInfinite';

import { DependentTabs } from './components/DependentTabs';

import { OperationViewer } from './components/Operations';
import * as CommandUtils from './components/CommandUtils';
import * as utils from './components/utils';
import { StatusBar } from './components/StatusBar';

// In case of classic Jupyter Notebook and embed, we provide the PhosphorJS CSS
export * from './version';
export * from './dcefwidget';

export const extraComponents = {
  ColumnsEditor,
  DependentTabs,
  OperationViewer,
  WidgetDCFCell,
  DFViewer,
  DFViewerInfinite,
  StaticWrapDFViewerInfinite,
  StatusBar,
  HistogramCell,
  CommandUtils,
  utils,
  InfiniteWidgetDCFCell: BuckarooInfiniteWidget,
  InfiniteEx,
};
