import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/inter";
import "@/styles/globals.css";

import { App } from "@/app/App";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("OrgAtlas could not find the application root.");
}

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);