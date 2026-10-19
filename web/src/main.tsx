import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ApiProvider } from "./api/ApiProvider";
import { exchangeBootstrap } from "./api/bootstrap";
import { createQueryClient } from "./api/queries";
import { applyTheme, readPreferences } from "./lib/preferences";
import "./styles/tokens.css";
import "./styles/app.css";

// Apply the stored theme before the first render to avoid a flash of the wrong theme.
applyTheme(readPreferences().theme);

const root = document.getElementById("root");
if (root === null) throw new Error("Missing #root element");

const queryClient = createQueryClient();

// Exchange the launch-link secret for the session cookie before the first
// API call. The exchange removes the secret from the address bar first.
void exchangeBootstrap().finally(() => {
  createRoot(root).render(
    <StrictMode>
      <ApiProvider>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ApiProvider>
    </StrictMode>,
  );
});
