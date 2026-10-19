import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { json, UPLOAD_LIMIT } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { settingsServer } from "./test/fixtures";

const MIB = 1024 * 1024;

function limit(overrides: Partial<typeof UPLOAD_LIMIT> = {}) {
  return { ...UPLOAD_LIMIT, ...overrides };
}

async function openPanel(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings", server);
  const user = userEvent.setup();
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  await user.click(screen.getByRole("button", { name: "Workspace" }));
  const panel = await screen.findByRole("region", { name: "Upload limit" });
  return { server, user, panel };
}

describe("upload limit panel", () => {
  it("states the limit in force, that the default applies and that a change applies straight away", async () => {
    const { panel } = await openPanel();
    expect(await within(panel).findByText("The limit in force is 50 MiB per file.")).toBeInTheDocument();
    expect(panel).toHaveTextContent("No limit is saved, so the default of 50 MiB applies.");
    expect(panel).toHaveTextContent("A change applies to new uploads straight away.");
    expect(within(panel).getByText("default")).toBeInTheDocument();
    expect(within(panel).queryByRole("spinbutton")).toBeNull();
  });

  it("opens the input filled with the limit in force and names the allowed range", async () => {
    const { user, panel } = await openPanel();
    await user.click(await within(panel).findByRole("button", { name: "Edit Limit per file, in MiB" }));
    expect(within(panel).getByRole("spinbutton", { name: "Limit per file, in MiB" })).toHaveValue(50);
    expect(panel).toHaveTextContent("Allowed: 1 to 2048 MiB.");
  });

  it("saves a new limit as a whole number of MiB with the revision and shows what the server returned", async () => {
    let saved: number | null = null;
    const state = () => limit({ max_bytes: (saved ?? 50) * MIB, source: saved === null ? "default" : "config-file", saved_mib: saved });
    const { server, user, panel } = await openPanel({
      "GET /v1/settings/upload-limit": state,
      "PUT /v1/settings/upload-limit": (body: Record<string, unknown>) => {
        saved = body.max_mib as number | null;
        return state();
      },
    });
    await user.click(await within(panel).findByRole("button", { name: "Edit Limit per file, in MiB" }));
    const input = within(panel).getByRole("spinbutton", { name: "Limit per file, in MiB" });
    await user.clear(input);
    await user.type(input, "200");
    await user.click(within(panel).getByRole("button", { name: "Save" }));
    expect(await within(panel).findByText("The limit in force is 200 MiB per file.")).toBeInTheDocument();
    expect(within(panel).getByText("from omrg.jsonc")).toBeInTheDocument();
    expect(server.find("PUT", "/v1/settings/upload-limit").map((call) => call.body)).toEqual([{ max_mib: 200, revision: "r1" }]);
  });

  it("returns to the default and says the default applies", async () => {
    let saved: number | null = 200;
    const state = () => limit({ max_bytes: (saved ?? 64) * MIB, source: saved === null ? "default" : "config-file", saved_mib: saved, default_mib: 64 });
    const { server, user, panel } = await openPanel({
      "GET /v1/settings/upload-limit": state,
      "PUT /v1/settings/upload-limit": () => {
        saved = null;
        return state();
      },
    });
    await user.click(await within(panel).findByRole("button", { name: "Edit Limit per file, in MiB" }));
    await user.click(within(panel).getByRole("button", { name: "Use default" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/upload-limit").map((call) => call.body)).toEqual([{ max_mib: null, revision: "r1" }]));
    expect(await within(panel).findByText("No limit is saved, so the default of 64 MiB applies.")).toBeInTheDocument();
  });

  it("refuses a value outside the reported range, or not a whole number, before any request", async () => {
    const { server, user, panel } = await openPanel({ "GET /v1/settings/upload-limit": () => limit({ min_mib: 2, max_mib: 300 }) });
    await user.click(await within(panel).findByRole("button", { name: "Edit Limit per file, in MiB" }));
    const field = within(panel).getByLabelText("Limit per file, in MiB");
    for (const value of ["1", "301", "1.5"]) {
      await user.clear(field);
      await user.type(field, value);
      await user.click(within(panel).getByRole("button", { name: "Save" }));
      expect(within(panel).getByText("Enter a whole number from 2 to 300.")).toBeInTheDocument();
    }
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(server.find("PUT", "/v1/settings/upload-limit")).toHaveLength(0);
  });

  it("shows the rule message of the server when a save is refused", async () => {
    const message = "The limit must be a whole number from 1 to 2048 MiB.";
    const { user, panel } = await openPanel({ "PUT /v1/settings/upload-limit": () => json({ status: "error", message }, 400) });
    await user.click(await within(panel).findByRole("button", { name: "Edit Limit per file, in MiB" }));
    const field = within(panel).getByLabelText("Limit per file, in MiB");
    await user.clear(field);
    await user.type(field, "200");
    await user.click(within(panel).getByRole("button", { name: "Save" }));
    expect(await within(panel).findByRole("alert")).toHaveTextContent(message);
  });

  it("shows a limit set at launch with no form, naming the flag and the variable", async () => {
    const { panel } = await openPanel({ "GET /v1/settings/upload-limit": () => limit({ max_bytes: 400 * MIB, source: "launch", saved_mib: 200 }) });
    expect(await within(panel).findByText("The limit in force is 400 MiB per file.")).toBeInTheDocument();
    expect(panel).toHaveTextContent("The limit was set when the server started.");
    expect(within(panel).getByText("--max-upload-mib").tagName).toBe("CODE");
    expect(within(panel).getByText("WEB_MAX_UPLOAD_MIB").tagName).toBe("CODE");
    expect(within(panel).queryByRole("textbox")).toBeNull();
    expect(within(panel).queryByRole("spinbutton")).toBeNull();
    expect(within(panel).queryByRole("button")).toBeNull();
  });

  it("shows one friendly line with Retry when the limit cannot be read, then recovers", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    const { user, panel } = await openPanel({
      "GET /v1/settings/upload-limit": () => (fail ? json({ status: "error", message: "RAW boom" }, 500) : limit()),
    });
    const alert = await within(panel).findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(panel).not.toHaveTextContent("RAW boom");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await within(panel).findByText("The limit in force is 50 MiB per file.")).toBeInTheDocument();
  });
});
