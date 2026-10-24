import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Integration, IntegrationInstall } from "../api/integrations";
import { documentsServer, json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const SOURCE = "~/src/omrs";

function entry(id: string, name: string, change: Partial<Integration> = {}): Integration {
  return {
    id,
    name,
    purpose: `Purpose of ${id}.`,
    extra: id,
    install_command: `uv tool install --reinstall "omrs[web,hybrid,${id}] @ ${SOURCE}"`,
    pip_command: `pip install "omrs[${id}]"`,
    availability: "not-installed",
    installable: true,
    install_reason: null,
    packages: [`package-for-${id}>=1.0`],
    install_caution: null,
    ...change,
  };
}

const ANTHROPIC = entry("anthropic", "Anthropic provider", { packages: ["llama-index-llms-anthropic>=0.11.0"] });
const AZURE = entry("azure", "Azure Document Intelligence");
const WEB = entry("web", "Local web workspace", { availability: "available", installable: false, install_reason: "not-installable-here", packages: [] });

const IDLE: IntegrationInstall = { state: "idle", extra: null, started_at: null, finished_at: null, reason: null, exit_code: null, output: [] };
const RUNNING: IntegrationInstall = { ...IDLE, state: "running", extra: "anthropic", started_at: "2026-10-24T10:00:00Z", output: ["Resolving"] };
const SUCCEEDED: IntegrationInstall = { ...RUNNING, state: "succeeded", finished_at: "2026-10-24T10:00:30Z", exit_code: 0, output: ["Installed 3 packages"] };
const FAILED: IntegrationInstall = {
  ...RUNNING,
  state: "failed",
  finished_at: "2026-10-24T10:00:30Z",
  reason: "exit-code",
  exit_code: 1,
  output: Array.from({ length: 40 }, (_, index) => `output line ${index + 1}`),
};

/** A server whose install state the test moves on by hand. */
function installServer(options: { install?: IntegrationInstall; catalogue?: Integration[]; post?: Handler } = {}) {
  const state = { install: options.install ?? IDLE, catalogue: options.catalogue ?? [ANTHROPIC, AZURE, WEB] };
  const server = documentsServer({
    "GET /v1/integrations": () => ({ status: "ok", install_type: "uv-tool", integrations: state.catalogue }),
    "GET /v1/integrations/install": () => ({ status: "ok", install: state.install }),
    "POST /v1/integrations/:extra/install":
      options.post ??
      ((_body, call) => {
        state.install = { ...RUNNING, extra: call.path.split("/")[3] ?? null };
        return json({ status: "ok", install: state.install }, 202);
      }),
    "GET /v1/server/power": () => ({ managed: true }),
  });
  return { server, state };
}

const card = async (name: string) => {
  const list = await screen.findByRole("list", { name: "Integrations" });
  const item = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name }) !== null);
  if (item === undefined) throw new Error(`No card named ${name}`);
  return item;
};

const advance = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
const statusReads = (server: ReturnType<typeof documentsServer>) => server.find("GET", "/v1/integrations/install").length;
// `find` matches a path prefix, so count the catalogue reads by exact path.
const listReads = (server: ReturnType<typeof documentsServer>) => server.calls.filter((call) => call.method === "GET" && call.path === "/v1/integrations").length;

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function setup() {
  return userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
}

async function pressInstall(name: string) {
  const user = setup();
  await user.click(within(await card(name)).getByRole("button", { name: `Install ${name}` }));
  const dialog = await screen.findByRole("dialog", { name: `Install ${name}?` });
  return { user, dialog };
}

describe("Install from the Integrations page", () => {
  it("installs Anthropic: posts, shows progress, then Installed, restart to use with Restart", async () => {
    const { server, state } = installServer();
    startApp("#/integrations", server);
    const { user, dialog } = await pressInstall("Anthropic provider");
    expect(dialog).toHaveTextContent("anthropic");
    expect(within(dialog).getByRole("list", { name: "Packages" })).toHaveTextContent("llama-index-llms-anthropic>=0.11.0");
    expect(dialog).toHaveTextContent(/restart/i);
    await user.click(within(dialog).getByRole("button", { name: "Install" }));

    await waitFor(() => expect(server.find("POST", "/v1/integrations/anthropic/install")).toHaveLength(1));
    const anthropic = await card("Anthropic provider");
    expect(await within(anthropic).findByRole("status")).toHaveTextContent(/Installing/);

    state.install = SUCCEEDED;
    state.catalogue = [{ ...ANTHROPIC, availability: "restart-needed", installable: false, install_reason: "already-installed" }, AZURE, WEB];
    await advance(1100);
    await waitFor(() => expect(within(anthropic).getByText("Installed, restart to use", { selector: "[data-slot=badge]" })).toBeInTheDocument());
    await user.click(within(anthropic).getByRole("button", { name: "Restart" }));
    expect(await screen.findByRole("dialog", { name: "Restart to apply?" })).toHaveTextContent("Anthropic provider applies after a restart.");
  });

  it("calls nothing when the dialog is cancelled", async () => {
    const { server } = installServer();
    startApp("#/integrations", server);
    const { user, dialog } = await pressInstall("Anthropic provider");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await advance(2000);
    expect(server.calls.filter((call) => call.method === "POST")).toHaveLength(0);
  });

  it("disables every other Install button while an install runs", async () => {
    const { server } = installServer({ install: RUNNING });
    startApp("#/integrations", server);
    const azure = await card("Azure Document Intelligence");
    await waitFor(() => expect(within(azure).getByRole("button", { name: "Install Azure Document Intelligence" })).toBeDisabled());
    expect(within(await card("Anthropic provider")).getByRole("status")).toHaveTextContent(/Installing/);
  });

  it("shows the last output lines and a Retry action when the install fails", async () => {
    const { server } = installServer({ install: FAILED });
    startApp("#/integrations", server);
    const anthropic = await card("Anthropic provider");
    const alert = await within(anthropic).findByRole("alert");
    expect(alert).toHaveTextContent(/install failed/i);
    const output = within(anthropic).getByLabelText("Install output for Anthropic provider");
    expect(output).toHaveTextContent("output line 1");
    expect(output).toHaveTextContent("output line 40");
    expect(output.className).toMatch(/overflow-auto/);
    await setup().click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/anthropic/install")).toHaveLength(1));
  });

  it("says another install is running when the server refuses with install-running, and Retry posts again", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = installServer({
      post: () => json({ status: "error", message: "Refused <raw> detail", reason: "install-running" }, 409),
    });
    startApp("#/integrations", server);
    const { user, dialog } = await pressInstall("Anthropic provider");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    const alert = await within(await card("Anthropic provider")).findByRole("alert");
    expect(alert).toHaveTextContent("Another install is running. Wait for it to finish, then try again.");
    expect(alert).not.toHaveTextContent("Refused");
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(server.find("POST", "/v1/integrations/anthropic/install")).toHaveLength(2));
  });

  it("falls back to the general friendly line for a refusal reason it does not know", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = installServer({
      post: () => json({ status: "error", message: "Refused <raw> detail", reason: "something-new" }, 409),
    });
    startApp("#/integrations", server);
    const { user, dialog } = await pressInstall("Anthropic provider");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    const alert = await within(await card("Anthropic provider")).findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Refused");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows Installed, restart to use and Restart for an entry the server reports as restart-needed", async () => {
    const { server } = installServer({ catalogue: [{ ...ANTHROPIC, availability: "restart-needed", installable: false, install_reason: "already-installed" }, WEB] });
    startApp("#/integrations", server);
    const anthropic = await card("Anthropic provider");
    expect(within(anthropic).getByText("Installed, restart to use", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(anthropic).getByRole("button", { name: "Restart" })).toBeInTheDocument();
    expect(within(anthropic).queryByRole("button", { name: /^Install/ })).toBeNull();
  });

  it("trusts the server after a restart: an available entry shows Installed even when the last status read said succeeded", async () => {
    // A login item restart signs the page in again without a reload, so the cached status can still say succeeded.
    const { server } = installServer({
      install: SUCCEEDED,
      catalogue: [{ ...ANTHROPIC, availability: "available", installable: false, install_reason: "already-installed" }, WEB],
    });
    startApp("#/integrations", server);
    const anthropic = await card("Anthropic provider");
    await waitFor(() => expect(statusReads(server)).toBe(1));
    expect(within(anthropic).getByText("Installed", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(anthropic).queryByRole("button", { name: "Restart" })).toBeNull();
  });

  it("shows no Install button on an entry that is not installable, only its command", async () => {
    const { server } = installServer();
    startApp("#/integrations", server);
    const web = await card("Local web workspace");
    expect(within(web).queryByRole("button", { name: /^Install/ })).toBeNull();
    expect(web).toHaveTextContent('uv tool install --reinstall "omrs[web,hybrid,web] @ ~/src/omrs"');
  });

  it("says under a uv tool command that it keeps the extra after a later reinstall", async () => {
    const { server } = installServer();
    startApp("#/integrations", server);
    expect(await card("Azure Document Intelligence")).toHaveTextContent(/keeps the extra after a later reinstall/i);
  });

  it("says Install adds the packages and a restart makes them available", async () => {
    const { server } = installServer();
    startApp("#/integrations", server);
    const notice = await screen.findByRole("note");
    await waitFor(() => expect(notice).toHaveTextContent(/Install adds the packages/i));
    expect(notice).toHaveTextContent(/restart makes them available/i);
  });
});

const CAUTION = "This install can change another package. It adds Amazon's botocore, which needs python-dateutil below version 3.";

describe("Install caution and post-install check", () => {
  it("shows the caution in a red callout before the Install button while the entry is not installed", async () => {
    const { server } = installServer({ catalogue: [{ ...ANTHROPIC, install_caution: CAUTION }, AZURE, WEB] });
    startApp("#/integrations", server);
    const anthropic = await card("Anthropic provider");
    const callout = within(anthropic).getByText(CAUTION).closest("[data-slot=install-caution]");
    expect(callout).not.toBeNull();
    expect(callout).toHaveTextContent(/^Before you install/);
    expect(callout?.className).toMatch(/border-status-error/);
    const install = within(anthropic).getByRole("button", { name: "Install Anthropic provider" });
    expect(callout!.compareDocumentPosition(install) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(await card("Azure Document Intelligence")).queryByText(/Before you install/)).toBeNull();
  });

  it("hides the caution once the entry is available or waits for a restart", async () => {
    const available = { ...ANTHROPIC, install_caution: CAUTION, availability: "available" as const, installable: false, install_reason: "already-installed" as const };
    const restart = { ...AZURE, install_caution: CAUTION, availability: "restart-needed" as const, installable: false, install_reason: "already-installed" as const };
    const { server } = installServer({ catalogue: [available, restart, WEB] });
    startApp("#/integrations", server);
    expect(within(await card("Anthropic provider")).queryByText(CAUTION)).toBeNull();
    expect(within(await card("Azure Document Intelligence")).queryByText(CAUTION)).toBeNull();
  });

  it("says the packages clash and to run the command when the check after the install fails, with no Retry", async () => {
    const { server } = installServer({ install: { ...FAILED, reason: "check-failed", output: ["pandas needs python-dateutil>=3"] } });
    startApp("#/integrations", server);
    const anthropic = await card("Anthropic provider");
    const alert = await within(anthropic).findByRole("alert");
    expect(alert).toHaveTextContent("The packages were installed, but they clash with packages the server already has. Do not restart yet: run the command below to reinstall cleanly.");
    expect(within(alert).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(within(anthropic).getByLabelText("Install output for Anthropic provider")).toHaveTextContent("pandas needs python-dateutil>=3");
  });

  it("says the server could not check the entry when it refuses with status-unknown", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { server } = installServer({
      post: () => json({ status: "error", message: "Refused <raw> detail", reason: "status-unknown" }, 409),
    });
    startApp("#/integrations", server);
    const { user, dialog } = await pressInstall("Anthropic provider");
    await user.click(within(dialog).getByRole("button", { name: "Install" }));
    const alert = await within(await card("Anthropic provider")).findByRole("alert");
    expect(alert).toHaveTextContent("The server could not check this integration, so it cannot install it. Run the command instead.");
    expect(within(alert).getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });
});

describe("Install status polling", () => {
  it("reads the status once and sends no more requests while idle", async () => {
    const { server } = installServer();
    startApp("#/integrations", server);
    await card("Anthropic provider");
    await waitFor(() => expect(statusReads(server)).toBe(1));
    await advance(5000);
    expect(statusReads(server)).toBe(1);
  });

  it("polls every second while running and stops after succeeded", async () => {
    const { server, state } = installServer({ install: RUNNING });
    startApp("#/integrations", server);
    await card("Anthropic provider");
    await waitFor(() => expect(statusReads(server)).toBe(1));
    await advance(1100);
    await waitFor(() => expect(statusReads(server)).toBe(2));
    const before = listReads(server);
    state.install = SUCCEEDED;
    await advance(1100);
    await waitFor(() => expect(statusReads(server)).toBe(3));
    await waitFor(() => expect(listReads(server)).toBe(before + 1));
    await advance(5000);
    expect(statusReads(server)).toBe(3);
  });

  it("sends no status request when the server cannot install", async () => {
    const server = documentsServer({
      "GET /v1/integrations": () => ({ status: "ok", install_type: "checkout", integrations: [{ ...ANTHROPIC, installable: false, install_reason: "not-uv-tool" }] }),
    });
    startApp("#/integrations", server);
    await card("Anthropic provider");
    await advance(3000);
    expect(statusReads(server)).toBe(0);
  });
});

describe("Link to one entry", () => {
  it("focuses the entry the address names", async () => {
    const { server } = installServer();
    startApp("#/integrations/anthropic", server);
    await card("Anthropic provider");
    await waitFor(() => expect(document.activeElement?.id).toBe("integration-anthropic"));
  });
});
