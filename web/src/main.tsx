import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { exchangeBootstrap } from "./api/bootstrap";
import { applyTheme, readUiState } from "./lib/preferences";
import "./styles/tokens.css";
import "./styles/app.css";

// Apply the stored theme before the first render to avoid a flash of the wrong theme.
applyTheme(readUiState().theme);

const root = document.getElementById("root");
if (root === null) throw new Error("Missing #root element");

// Exchange the launch-link secret for the session cookie before the first
// API call. The exchange removes the secret from the address bar first.
void exchangeBootstrap().finally(() => {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
