import App from "../App";
import { documentsServer } from "./fakeDocumentsServer";
import { renderWithProviders } from "./providers";

/** Renders the whole app at a hash against a fixture server, the way a view test reaches its view. */
export function startApp(hash: string, server = documentsServer()) {
  window.history.replaceState(null, "", `/${hash}`);
  return { server, ...renderWithProviders(<App />, { fetchImpl: server.fetchImpl }) };
}
