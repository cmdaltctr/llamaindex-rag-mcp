import userEvent from "@testing-library/user-event";
import type { Handler } from "../../test/fakeDocumentsServer";
import { startApp } from "../../test/startApp";
import { experimentsServer, type ServerState } from "./experimentsServer";

/** Renders the whole app at an Experiments hash against the fixture server. */
export function openExperiments(initial: Partial<ServerState> = {}, extra: Record<string, Handler> = {}, hash = "#/experiments") {
  const server = experimentsServer(initial, extra);
  startApp(hash, server);
  return { server, user: userEvent.setup() };
}
