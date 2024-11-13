/* eslint-disable @typescript-eslint/ban-ts-comment */
import 'bootstrap/dist/css/bootstrap.min.css';
import React from 'react';
import { HashRouter as Router, Route, Link } from 'react-router-dom';
import { Button } from 'react-bootstrap';

import './app.css';


const examples = {
  WidgetDCFCellEx: {
    title: 'WigetDCFCell',
    file: 'WidgetDCFCellEx',
    layout: 'HBox',
  },
  ColumnsEditorEx: {
    title: 'ColumnsEditor',
    file: 'ColumnsEditorEx',
    layout: 'HBox',
  },
  CommandViewerEx: {
    title: 'CommandViewer',
    file: 'CommandViewerEx',
    layout: 'HBox',
  },
  DFViewerEx: { title: 'DFViewer', file: 'DFViewerEx', layout: 'HBox' },
  DFViewerEx_string_index: {
    title: 'DFViewer string index',
    file: 'DFViewerEx_string_index',
    layout: 'HBox',
  },
  DFViewerEx_large: {
    title: 'DFViewer large',
    file: 'DFViewerEx_large',
    layout: 'VBox',
  },
  DFViewerInfiniteEx_large: {
    title: 'DFViewerInfinite large',
    file: 'DFViewerInfiniteEx_large',
    layout: 'VBox',
  },

  DFViewerEx_real_summary: {
    title: 'DFViewer summary',
    file: 'DFViewerEx_real_summary',
    layout: 'HBox',
  },
  DFViewerEx_short_data: {
    title: 'DFViewer short_data',
    file: 'DFViewerEx_short_data',
    layout: 'HBox',
  },

  StatusBarEx: { title: 'StatusBar', file: 'StatusBarEx', layout: 'VBox' },
  InfiniteEx: { title: 'Infinite Example', file: 'InfiniteEx', layout: 'VBox' },

  HistogramEx: { title: 'Histogram', file: 'HistogramEx', layout: 'HBox' },
};

// The examples use a code-loading technique that I have described in
// https://mmomtchev.medium.com/making-examples-displaying-code-along-its-output-with-webpack-a28dcf5439c6

const ReadmeBlock = React.lazy(
  () => import(/* webpackPrefetch: true */ './ReadmeBlock')
);
const CodeBlock = React.lazy(
  () => import(/* webpackPrefetch: true */ './CodeBlock')
);

for (const ex of Object.keys(examples)) {
  examples[ex].comp = React.lazy(
    () => import(/* webpackPrefetch: true */ `./ex/${examples[ex].file}.tsx`)
  );
  examples[ex].code = import(
    /* webpackPrefetch: true */ `!!html-loader?{"minimize":false}!./jsx-loader.ts!./ex/${examples[ex].file}.tsx`
  ).then((code) => code.default);
  examples[ex].text = import(
    /* webpackPrefetch: true */ `!!raw-loader!./ex/${examples[ex].file}.tsx`
  ).then((text) => text.default);
}

const LeftMenuItem = (props): JSX.Element => (
  <Link to={props.id}>
    <Button className="w-100" variant="light">
      {props.title}
    </Button>
  </Link>
);

// eslint-disable-next-line no-var
//declare var VERSION: string = "handwritten";

const RenderEl = (ex: any): JSX.Element => {
  if (ex.layout === 'HBox') {
    return (
      <div className="row">
        <div className="col-12 col-xl-5 mb-1">
          <React.Suspense fallback={<div>Loading component...</div>}>
            <div className="component-example">
              <h2> Component example </h2>
              {React.createElement(ex.comp)}
            </div>
          </React.Suspense>
        </div>
        <div className="col-12 col-xl-7">
          <React.Suspense fallback={<div>Parsing code...</div>}>
            <CodeBlock title={ex.title} code={ex.code} text={ex.text} />
          </React.Suspense>
        </div>
      </div>
    );
  } else {
    return (
      <div className="row">
        <div className="row">
          <React.Suspense fallback={<div>Loading component...</div>}>
            <div className="component-example">
              <h2> Component example </h2>
              {React.createElement(ex.comp)}
            </div>
          </React.Suspense>
        </div>
        <div className="row">
          <React.Suspense fallback={<div>Parsing code...</div>}>
            <CodeBlock title={ex.title} code={ex.code} text={ex.text} />
          </React.Suspense>
        </div>
      </div>
    );
  }
};

const App = (): JSX.Element => {
  const [jsText, setJSText] = React.useState<string>('');

  return (
    <Router>
      <h1 className="m-2">
        <strong>Buckaroo JS Frontend Examples</strong>
      </h1>
      <div className="d-flex flex-row p-3">
        <div className="d-flex flex-column left-menu me-2">
          <LeftMenuItem id={''} title={'Home'} />
          {Object.keys(examples).map((e) => (
            <LeftMenuItem key={e} id={e} title={examples[e].title} />
          ))}
        </div>
        <div className="d-flex flex-column w-100 overflow-hidden">
          <div className="fluid-container">
            <Route exact path="/">
              <div className="ml-2">
                <React.Suspense fallback={<div>Loading...</div>}>
                  <ReadmeBlock />
                </React.Suspense>
              </div>
            </Route>
            {Object.keys(examples).map((e) => (
              <Route key={e} path={`/${e}`}>
                {RenderEl(examples[e])}
              </Route>
            ))}
          </div>
        </div>
      </div>
    </Router>
  );
};

export default App;
