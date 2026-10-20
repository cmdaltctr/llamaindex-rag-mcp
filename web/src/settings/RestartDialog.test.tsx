import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { RestartDialog } from "./RestartDialog";

const MANAGED: Record<string, Handler> = { "GET /v1/server/power": () => ({ managed: true }) };
const FOREGROUND: Record<string, Handler> = { "GET /v1/server/power": () => ({ managed: false }) };
const ACCEPTED: Handler = () => json({ status: "accepted", action: "restart" }, 202);

function open(handlers: Record<string, Handler>, change: string | null = "Port 9100", plural = false) {
  const server = documentsServer(handlers);
  const onLater = vi.fn();
  renderWithProviders(<RestartDialog change={change} plural={plural} onLater={onLater} />, { fetchImpl: server.fetchImpl });
  return { server, onLater, user: userEvent.setup() };
}

describe("RestartDialog", () => {
  it("renders nothing without a change", () => {
    open(MANAGED, null);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("names the change and offers Restart now and Later for the login item", async () => {
    open(MANAGED);
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("Port 9100 applies after a restart.");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Restart now" })).toBeEnabled());
    expect(within(dialog).getByRole("button", { name: "Later" })).toBeInTheDocument();
  });

  it("uses the plural verb for several changes", async () => {
    open(MANAGED, "Two settings", true);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Two settings apply after a restart.");
  });

  it("posts the restart, says the page signs in again by itself and names omrg web open", async () => {
    const { user, server } = open({ ...MANAGED, "POST /v1/server/power": ACCEPTED });
    const dialog = await screen.findByRole("dialog");
    const button = within(dialog).getByRole("button", { name: "Restart now" });
    await waitFor(() => expect(button).toBeEnabled());
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);
    await user.click(button);
    await waitFor(() => expect(server.find("POST", "/v1/server/power")).toHaveLength(1));
    expect(server.find("POST", "/v1/server/power")[0]?.body).toEqual({ action: "restart" });
    expect(await within(dialog).findByText(/^Restarting\./)).toHaveTextContent(/signs in again by itself/);
    expect(within(dialog).getByText("omrg web open")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Restart now" })).not.toBeInTheDocument();
  });

  it("shows the command and no Restart now when the server runs in a terminal", async () => {
    const { server } = open(FOREGROUND);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByText("omrg web")).toBeInTheDocument());
    expect(dialog).toHaveTextContent(/runs in a terminal/i);
    expect(within(dialog).queryByRole("button", { name: "Restart now" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Later" })).toBeInTheDocument();
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);
  });

  it("shows the command when the power route does not answer", async () => {
    open({ "GET /v1/server/power": () => json({ detail: "no" }, 404) });
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByText("omrg web")).toBeInTheDocument());
    expect(within(dialog).queryByRole("button", { name: "Restart now" })).not.toBeInTheDocument();
  });

  it("calls onLater and posts nothing on Later", async () => {
    const { user, server, onLater } = open({ ...MANAGED, "POST /v1/server/power": ACCEPTED });
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Restart now" })).toBeEnabled());
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    expect(onLater).toHaveBeenCalledOnce();
    expect(server.find("POST", "/v1/server/power")).toHaveLength(0);
  });

  it("treats Escape as Later", async () => {
    const { user, onLater } = open(MANAGED);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(onLater).toHaveBeenCalledOnce();
  });

  it("shows one busy line on a 409 and offers a retry", async () => {
    const { user } = open({ ...MANAGED, "POST /v1/server/power": () => json({ status: "error", message: "An ingestion is running." }, 409) });
    const dialog = await screen.findByRole("dialog");
    const button = within(dialog).getByRole("button", { name: "Restart now" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/busy/i);
    expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/^Restarting\./)).not.toBeInTheDocument();
  });
});
