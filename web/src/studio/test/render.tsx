import userEvent from "@testing-library/user-event";
import App from "../../App";
import { renderWithProviders } from "../../test/providers";
import { fakeServer, type FakeServerOptions } from "./fakeServer";

/** Renders the whole app at a hash against the Studio fixture server. */
export function openStudio(hash = "#/studio", options: FakeServerOptions = {}) {
  const server = fakeServer({ templates: [], failures: {}, ...options });
  window.history.replaceState(null, "", `/${hash}`);
  const user = userEvent.setup();
  const view = renderWithProviders(<App />, { fetchImpl: server.fetchImpl });
  return { server, user, view };
}
