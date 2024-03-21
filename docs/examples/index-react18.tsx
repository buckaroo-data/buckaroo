import React from 'react';
import ReactDOMClient from 'react-dom/client';

import App from './App';

// eslint-disable-next-line no-console
console.debug('React 18 mode');
ReactDOMClient.createRoot(document.getElementById('root')).render(<App />);
