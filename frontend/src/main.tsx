import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// the Papier look's type, bundled so that no page asks Google for it; a browser fetches a
// face only once a page uses it, so the classic look downloads none of these
import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-sans/700.css";
import "@fontsource/fraunces/500.css";
import "@fontsource/fraunces/600.css";
// the wordmark's face (the logo, docs/brand/), in every look
import "@fontsource/montserrat/700.css";
import "./index.css";
import "./styles/theme.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
