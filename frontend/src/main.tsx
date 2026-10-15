import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import "@/styles/globals.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("OrgAtlas could not find the application root.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
