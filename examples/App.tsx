/* eslint-disable @typescript-eslint/ban-ts-comment */
import 'bootstrap/dist/css/bootstrap.min.css';
import React from 'react';
import {HashRouter as Router, Route, Link} from 'react-router-dom';
//import {Button} from 'react-bootstrap';

import './app.css';

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import '../js/style/dcf-npm.css';


const examples = {
    WidgetDCFCellEx: {title: 'WigetDCFCell', file: 'WidgetDCFCellEx'},
    ColumnsEditorEx: {title: 'ColumnsEditor', file: 'ColumnsEditorEx'},
    CommandViewerEx: {title: 'CommandViewer', file: 'CommandViewerEx'},
    DFViewerEx: {title: 'DFViewer', file: 'DFViewerEx'},
    DFViewerEx_string_index: {title: 'DFViewer string index', file: 'DFViewerEx_string_index'},
    DFViewerEx_large: {title: 'DFViewer large', file: 'DFViewerEx_large'},
    DFViewerEx_real_summary: {title: 'DFViewer summary', file: 'DFViewerEx_real_summary'},
    DFViewerEx_short_data: {title: 'DFViewer short_data', file: 'DFViewerEx_short_data'},

    StatusBarEx: {title: 'StatusBar', file: 'StatusBarEx'},
    HistogramEx: {title: 'Histogram', file: 'HistogramEx'}
};

for (const ex of Object.keys(examples)) {
    examples[ex].comp = React.lazy(
        () => import(/* webpackPrefetch: true */ `./ex/${examples[ex].file}.tsx`)
    );
  examples[ex].code = 'asfd'
  examples[ex].text = 'text'
}

const LeftMenuItem = (props): JSX.Element => (
  <div>
    <Link to={props.id}>
        <h3 className='w-100' variant='light'>
            {props.title}
        </h3>
    </Link>
    </div>
);


const App = (): JSX.Element => {
    const [jsText, setJSText] = React.useState<string>('');

    return (
        <Router>
	<div className="dev-examples">
            <h1 className='m-2'>
                <strong>buckaroo stuff examples </strong>
            </h1>
            <div className='d-flex flex-row p-3'>
                <div className='d-flex flex-column left-menu me-2'>
                    <LeftMenuItem id={''} title={'Home'} />
                    {Object.keys(examples).map((e) => (
                        <LeftMenuItem key={e} id={e} title={examples[e].title} />
                    ))}
                </div>
                <div className='d-flex flex-column w-100 overflow-hidden'>
                    <div className='fluid-container'>
                        <Route exact path='/'>
                            <div className='ml-2'>
                                <React.Suspense fallback={<div>Loading...</div>}>
                                </React.Suspense>
                            </div>
                        </Route>
                        {Object.keys(examples).map((e) => (
                            <Route key={e} path={`/${e}`}>
                                <div className='row'>
                                    <div className='col-12 col-xl-12 mb-12'>
                                        <React.Suspense fallback={<div>Loading component...</div>}>
                                            {React.createElement(examples[e].comp)}
                                        </React.Suspense>
                                    </div>
                                    <div className='col-12 col-xl-7'>
                                        <React.Suspense fallback={<div>Parsing code...</div>}>

                                        </React.Suspense>
                                    </div>
                                </div>
                            </Route>
                        ))}
                    </div>
                </div>
            </div>
	</div>
        </Router>
    );
};

export default App;
