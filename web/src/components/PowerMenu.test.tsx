import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { PowerMenu } from "./PowerMenu";

const HEALTH: Record<string, Handler> = { "GET /v1/health": () => ({ status: "ok", ready: true, version: "2.3.4" }) };
const MANAGED: Record<string, Handler> = { ...HEALTH, "GET /v1/server/power": () => ({ managed: true }) };
const FOREGROUND: Record<string, Handler> = { ...HEALTH, "GET /v1/server/power": () => ({ managed: false }) };
const ACCEPTED = (action: string): Handler => () => json({ status: "accepted", action }, 202);

async function openPanel(handlers: Record<string, Handler>) {
  const user = userEvent.setup();
  const server = documentsServer(handlers);
  renderWithProviders(<PowerMenu />, { fetchImpl: server.fetchImpl });
  await user.click(screen.getByRole("button", { name: /^Server status/ }));
  const panel = document.querySelector("[data-slot='power-panel']") as HTMLElement;
  return { user, server, panel };
}

/** The panel buttons are enabled once `GET /v1/server/power` answered managed. */
async function ready(panel: HTMLElement, name: string) {
  const button = within(panel).getByRole("button", { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

describe("PowerMenu", () => {
  it("opens a confirmation for Turn off and posts nothing until it is confirmed", async () => {
    const { user, server, panel } = await openPanel({ ...MANAGED, "POST /v1/server/power": ACCEPTED("off") });
    await user.click(await ready(panel, "Turn off"));
    const dialog = await screen.findByRole("dialog", { name: "Turn off OMRS?" });
    expect(dialog).toHaveTextContent(/stays off/i);
    expect(dialog).not.toHaveTextContent(/signed out/i);
    expect(within(dialog).getByText("omrs web start")).toBeInTheDocument();
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(server.find("POST", "/v1/server/power")).toHaveLength(1));
    expect(server.find("POST", "/v1/server/power")[0]?.body).toEqual({ action: "off" });
    expect(await screen.findByText(/^Turned off\./)).toBeInTheDocument();
    expect(screen.getAllByText("omrs web start").length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Restarting\./)).not.toBeInTheDocument();
  });

  it("opens a confirmation for Restart and posts nothing until it is confirmed", async () => {
    const { user, server, panel } = await openPanel({ ...MANAGED, "POST /v1/server/power": ACCEPTED("restart") });
    await user.click(await ready(panel, "Restart"));
    const dialog = await screen.findByRole("dialog", { name: "Restart OMRS?" });
    expect(dialog).toHaveTextContent(/signs in again by itself/i);
    expect(dialog).not.toHaveTextContent(/signed out/i);
    expect(within(dialog).getByText("omrs web open")).toBeInTheDocument();
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Restart" }));
    await waitFor(() => expect(server.find("POST", "/v1/server/power")).toHaveLength(1));
    expect(server.find("POST", "/v1/server/power")[0]?.body).toEqual({ action: "restart" });
    const done = await screen.findByText(/^Restarting\./);
    expect(done.parentElement).toHaveTextContent(/signs in again by itself/i);
    expect(screen.getAllByText("omrs web open").length).toBeGreaterThan(0);
  });

  it("posts nothing when the dialog is cancelled", async () => {
    const { user, server, panel } = await openPanel({ ...MANAGED, "POST /v1/server/power": ACCEPTED("off") });
    await user.click(await ready(panel, "Turn off"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);
    expect(screen.queryByText(/^Turned off\./)).not.toBeInTheDocument();
  });

  it("disables both buttons and names the terminal commands when the server is not managed", async () => {
    const { panel } = await openPanel(FOREGROUND);
    await waitFor(() => expect(within(panel).getByText(/runs in a terminal/i)).toBeInTheDocument());
    expect(within(panel).getByRole("button", { name: "Turn off" })).toBeDisabled();
    expect(within(panel).getByRole("button", { name: "Restart" })).toBeDisabled();
    expect(within(panel).getByText("omrs web restart")).toBeInTheDocument();
    expect(within(panel).getByText("omrs web open")).toBeInTheDocument();
  });

  it("disables both buttons with a reason when the power route does not answer", async () => {
    const { panel } = await openPanel({ ...HEALTH, "GET /v1/server/power": () => json({ detail: "no" }, 404) });
    await waitFor(() => expect(within(panel).getByText(/cannot tell whether/i)).toBeInTheDocument());
    expect(within(panel).getByRole("button", { name: "Turn off" })).toBeDisabled();
    expect(within(panel).getByRole("button", { name: "Restart" })).toBeDisabled();
    expect(within(panel).getByText("omrs web restart")).toBeInTheDocument();
  });

  it("shows one line on a 409 and does not report the app as off or restarting", async () => {
    const { user, server, panel } = await openPanel({
      ...MANAGED,
      "POST /v1/server/power": () => json({ status: "error", message: "An ingestion is running." }, 409),
    });
    await user.click(await ready(panel, "Turn off"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Turn off" }));
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent(/running|busy/i);
    expect(server.find("POST", "/v1/server/power")).toHaveLength(1);
    expect(screen.queryByText(/^Turned off\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Restarting\./)).not.toBeInTheDocument();
  });
});
