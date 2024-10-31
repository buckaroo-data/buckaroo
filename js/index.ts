// Copyright (c) Paddy Mullen
// Distributed under the terms of the Modified BSD License.

import { ColumnsEditor } from './components/ColumnsEditor';
import { DFViewer } from './components/DFViewerParts/DFViewer';
import { WidgetDCFCell } from './components/DCFCell';
import { HistogramCell } from './components/DFViewerParts/HistogramCell';
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
  StatusBar,
  HistogramCell,
  CommandUtils,
  utils,
};
