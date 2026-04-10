import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import "./i18n/config";
import App from "./App";
import { BackendStatusProvider } from "./context/BackendStatus";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <BackendStatusProvider>
        <App />
        <Toaster theme="dark" position="top-right" richColors closeButton />
      </BackendStatusProvider>
    </BrowserRouter>
  </React.StrictMode>
);
