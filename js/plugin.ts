// Copyright (c) Bloomberg
// Distributed under the terms of the Modified BSD License.

import { Application, IPlugin } from '@lumino/application';

import { Widget } from '@lumino/widgets';

import { IJupyterWidgetRegistry } from '@jupyter-widgets/base';

import { IThemeManager } from '@jupyterlab/apputils';

import { MODULE_NAME, MODULE_VERSION } from './version';
import * as dcefwidget from './dcefwidget';

const EXTENSION_ID = 'buckaroo:plugin';

/**
 * The datagrid plugin.
 */
const datagridPlugin: IPlugin<Application<Widget>, void> = {
  id: EXTENSION_ID,
  requires: [IJupyterWidgetRegistry],
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  optional: [IThemeManager as any],
  activate: activateWidgetExtension,
  autoStart: true,
};

export default datagridPlugin;

/**
 * Activate the widget extension.
 */
function activateWidgetExtension(
  app: Application<Widget>,
  registry: IJupyterWidgetRegistry,
  themeManager: IThemeManager | null
): void {
  console.log('buckaroo_widget plugin.ts after change EXTENSION_ID');
  // Exporting a patched DataGridView widget which handles dynamic theme changes
  registry.registerWidget({
    name: MODULE_NAME,
    version: MODULE_VERSION,
    exports: {
      ...dcefwidget,
    },
  });
}
