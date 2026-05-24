import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import HeightDemo from "./HeightDemo";

// Trivial path routing. The default app at "/" keeps the existing
// playground; "/height-demo" hosts the stacked autoHeight demo used by
// pw-tests/server-embed-height.spec.ts. Done with location.pathname
// rather than react-router to keep the example dependency-light.
const Root = location.pathname.startsWith("/height-demo") ? HeightDemo : App;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
