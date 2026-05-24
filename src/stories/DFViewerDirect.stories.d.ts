import { Meta, StoryObj } from '@storybook/react';
import { DFViewer } from '../components/DFViewerParts/DFViewerInfinite';
/**
 * Direct `<DFViewer>` consumer pattern — no wrapper component, no hooks
 * in a `render` function. `meta.component` is `DFViewer` itself and each
 * story passes prop values via `args:`, so Storybook's "Show code" view
 * displays the actual JSX an `npm install buckaroo-js-core` consumer
 * would paste into their React app (literal `df_data` array, literal
 * `df_viewer_config` object), not a `render()` arrow function.
 *
 * A `decorators` entry wraps the rendered output in a sized container —
 * decorators are not part of the "Show code" output, so they keep the
 * story functional without obscuring the consumer-facing API.
 */
declare const meta: Meta<typeof DFViewer>;
export default meta;
type Story = StoryObj<typeof meta>;
export declare const Primary: Story;
