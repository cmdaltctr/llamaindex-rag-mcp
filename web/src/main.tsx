import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ApiProvider } from "./api/ApiProvider";
import { createSessionRenewer, startSession, takePageSecret } from "./api/bootstrap";
import { createQueryClient } from "./api/queries";
import { applyTheme, readPreferences } from "./lib/preferences";
import "./styles/tokens.css";
import "./styles/app.css";

// Apply the stored theme before the first render to avoid a flash of the wrong theme.
applyTheme(readPreferences().theme);

const root = document.getElementById("root");
if (root === null) throw new Error("Missing #root element");

const queryClient = createQueryClient();

// Sign in before the first API call: with the launch-link secret when the
// address has one (the exchange removes it from the address bar first), else
// with the workspace secret that the server put into this page. The same
// secret signs the page in again after a server restart.
const pageSecret = takePageSecret();
const renewSession = pageSecret === null ? undefined : createSessionRenewer(pageSecret);
void startSession(renewSession ?? null).finally(() => {
  createRoot(root).render(
    <StrictMode>
      <ApiProvider renewSession={renewSession}>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </ApiProvider>
    </StrictMode>,
  );
});
