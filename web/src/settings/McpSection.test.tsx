import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { McpState } from "../api/settings";
import { json, type Handler } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { CONFIG_DIR, MCP_OFF, settingsServer, WEB_PORT } from "./test/fixtures";

const MCP_ON: McpState = { ...MCP_OFF, enabled: true };
const TOKEN = "omrg_mcp_Zq3xExampleTokenValue";

/** A stateful stand-in for the MCP routes, so a refetch sees what a write changed. */
function mcpRoutes(initial: McpState = MCP_OFF) {
  let state = initial;
  let port: number | null = null;
  const handlers: Record<string, Handler> = {
    "GET /v1/mcp": () => state,
    "PUT /v1/mcp": (body) => {
      state = { ...state, enabled: body.enabled as boolean };
      return state;
    },
    "POST /v1/mcp/token": () => {
      state = { ...state, token: { exists: true, created_at: "2026-10-14T10:00:00Z" } };
      return json({ status: "ok", token: TOKEN, created_at: "2026-10-14T10:00:00Z" }, 201);
    },
    "DELETE /v1/mcp/token": () => {
      const revoked = state.token.exists;
      state = { ...state, token: { exists: false, created_at: null } };
      return { status: "ok", revoked };
    },
    "GET /v1/settings/web-port": () => ({ ...WEB_PORT, saved: port }),
    "PUT /v1/settings/web-port": (body) => {
      port = body.port as number | null;
      return { ...WEB_PORT, saved: port };
    },
  };
  return handlers;
}

async function openMcp(handlers: Record<string, Handler> = mcpRoutes()) {
  const server = settingsServer(handlers);
  startApp("#/settings", server);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "MCP" }));
  await screen.findByRole("region", { name: "MCP" });
  return { server, user };
}

function panel(name: string) {
  return screen.getByRole("region", { name });
}

describe("MCP stdio configuration", () => {
  it("shows a configuration that runs uv with config_dir and copies it", async () => {
    const { user } = await openMcp();
    const stdio = await screen.findByRole("region", { name: "Stdio client" });
    expect(within(stdio).getByText(/uv run --directory/)).toBeInTheDocument();
    await user.click(within(stdio).getByRole("button", { name: "Copy stdio configuration" }));
    const copied = JSON.parse(await navigator.clipboard.readText()) as { mcpServers: { omrg: { command: string; args: string[] } } };
    expect(copied.mcpServers.omrg.command).toBe("uv");
    expect(copied.mcpServers.omrg.args).toEqual(["run", "--directory", CONFIG_DIR, "omrg"]);
    expect(await within(stdio).findByText("Copied stdio configuration.")).toBeInTheDocument();
  });

  it("shows the same configuration on the page", async () => {
    await openMcp();
    const stdio = await screen.findByRole("region", { name: "Stdio client" });
    expect(within(stdio).getByText(CONFIG_DIR, { exact: false, selector: "code" })).toBeInTheDocument();
  });

  it("shows a friendly line with Retry when config_dir cannot load", async () => {
    await openMcp({ ...mcpRoutes(), "GET /v1/connections": () => json({ status: "error", message: "boom" }, 500) });
    const stdio = await screen.findByRole("region", { name: "Stdio client" });
    expect(await within(stdio).findByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("MCP over HTTP switch", () => {
  it("shows the state the server reports", async () => {
    await openMcp();
    const http = await screen.findByRole("region", { name: "MCP over HTTP" });
    const toggle = await within(http).findByRole("switch", { name: "MCP over HTTP" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(toggle).toHaveTextContent("Off");
  });

  it("shows the state the server returns after the change, not an assumed state", async () => {
    // The server stays off whatever the request says.
    const stuck: Record<string, Handler> = { ...mcpRoutes(), "PUT /v1/mcp": () => MCP_OFF };
    const { user, server } = await openMcp(stuck);
    const toggle = await screen.findByRole("switch", { name: "MCP over HTTP" });
    await user.click(toggle);
    expect(server.find("PUT", "/v1/mcp")[0]?.body).toEqual({ enabled: true });
    expect(await screen.findByRole("switch", { name: "MCP over HTTP" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("switch", { name: "MCP over HTTP" })).toHaveTextContent("Off");
  });

  it("turns on when the server says on", async () => {
    const { user } = await openMcp();
    await user.click(await screen.findByRole("switch", { name: "MCP over HTTP" }));
    const toggle = await screen.findByRole("switch", { name: "MCP over HTTP", checked: true });
    expect(toggle).toHaveTextContent("On");
  });

  it("shows a friendly line when the change fails and keeps the old state", async () => {
    const { user } = await openMcp({ ...mcpRoutes(), "PUT /v1/mcp": () => json({ status: "error", message: "Unexpected token <" }, 500) });
    await user.click(await screen.findByRole("switch", { name: "MCP over HTTP" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(screen.queryByText(/Unexpected token/)).toBeNull();
    expect(screen.getByRole("switch", { name: "MCP over HTTP" })).toHaveAttribute("aria-checked", "false");
  });

  it("shows the HTTP client configuration with the server URL and copies it", async () => {
    const { user } = await openMcp(mcpRoutes(MCP_ON));
    const http = await screen.findByRole("region", { name: "MCP over HTTP" });
    expect(await within(http).findByText(MCP_ON.url, { exact: false, selector: "code" })).toBeInTheDocument();
    await user.click(within(http).getByRole("button", { name: "Copy HTTP configuration" }));
    const copied = JSON.parse(await navigator.clipboard.readText()) as { mcpServers: { omrg: { type: string; url: string; headers: Record<string, string> } } };
    expect(copied.mcpServers.omrg.type).toBe("http");
    expect(copied.mcpServers.omrg.url).toBe(MCP_ON.url);
    expect(copied.mcpServers.omrg.headers.Authorization).toBe("Bearer omrg_mcp_<token>");
  });
});

describe("MCP token", () => {
  it("says no token exists and offers Create", async () => {
    await openMcp();
    const token = await screen.findByRole("region", { name: "MCP token" });
    expect(await within(token).findByText("No token exists.")).toBeInTheDocument();
    expect(within(token).getByRole("button", { name: "Create token" })).toBeInTheDocument();
    expect(within(token).queryByRole("button", { name: "Revoke token" })).toBeNull();
  });

  it("shows a new token once with a copy action", async () => {
    const { user } = await openMcp();
    const token = await screen.findByRole("region", { name: "MCP token" });
    await user.click(await within(token).findByRole("button", { name: "Create token" }));
    expect(await within(token).findByText(TOKEN)).toBeInTheDocument();
    expect(within(token).getByText(/shown once/i)).toBeInTheDocument();
    await user.click(within(token).getByRole("button", { name: "Copy MCP token" }));
    expect(await navigator.clipboard.readText()).toBe(TOKEN);
    expect(await within(token).findByText("Copied MCP token.")).toBeInTheDocument();
  });

  it("does not show the token after the user leaves and reopens the MCP section", async () => {
    const { user } = await openMcp();
    const token = await screen.findByRole("region", { name: "MCP token" });
    await user.click(await within(token).findByRole("button", { name: "Create token" }));
    await within(token).findByText(TOKEN);
    await user.click(screen.getByRole("button", { name: "Runtime" }));
    await user.click(screen.getByRole("button", { name: "MCP" }));
    const reopened = await screen.findByRole("region", { name: "MCP token" });
    expect(await within(reopened).findByText(/A token exists/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(TOKEN);
    expect(window.localStorage.length === 0 || !JSON.stringify({ ...window.localStorage }).includes(TOKEN)).toBe(true);
    expect(window.sessionStorage.length === 0 || !JSON.stringify({ ...window.sessionStorage }).includes(TOKEN)).toBe(true);
  });

  it("states that rotation breaks existing clients, and rotates", async () => {
    const { user, server } = await openMcp(mcpRoutes({ ...MCP_ON, token: { exists: true, created_at: "2026-10-01T08:00:00Z" } }));
    const token = await screen.findByRole("region", { name: "MCP token" });
    expect(await within(token).findByText(/A token exists, created/)).toBeInTheDocument();
    expect(within(token).getByText(/Rotating the token stops every client that holds the old one/i)).toBeInTheDocument();
    await user.click(within(token).getByRole("button", { name: "Rotate token" }));
    expect(await within(token).findByText(TOKEN)).toBeInTheDocument();
    expect(server.find("POST", "/v1/mcp/token")).toHaveLength(1);
  });

  it("revokes the token and says so", async () => {
    const { user, server } = await openMcp(mcpRoutes({ ...MCP_ON, token: { exists: true, created_at: "2026-10-01T08:00:00Z" } }));
    const token = await screen.findByRole("region", { name: "MCP token" });
    await user.click(await within(token).findByRole("button", { name: "Revoke token" }));
    expect(await within(token).findByText("No token exists.")).toBeInTheDocument();
    expect(within(token).getByText("The token was revoked. Clients that hold it lose access at their next request.")).toBeInTheDocument();
    expect(server.find("DELETE", "/v1/mcp/token")).toHaveLength(1);
  });

  it("hides a shown token once it is revoked", async () => {
    const { user } = await openMcp();
    const token = await screen.findByRole("region", { name: "MCP token" });
    await user.click(await within(token).findByRole("button", { name: "Create token" }));
    await within(token).findByText(TOKEN);
    await user.click(within(token).getByRole("button", { name: "Revoke token" }));
    await within(token).findByText("No token exists.");
    expect(within(token).queryByText(TOKEN)).toBeNull();
  });

  it("shows a friendly line when creating fails", async () => {
    const { user } = await openMcp({ ...mcpRoutes(), "POST /v1/mcp/token": () => json({ status: "error", message: "Traceback" }, 500) });
    const token = await screen.findByRole("region", { name: "MCP token" });
    await user.click(await within(token).findByRole("button", { name: "Create token" }));
    expect(await within(token).findByRole("alert")).toHaveTextContent(/could not complete/i);
    expect(document.body.textContent).not.toContain("Traceback");
  });
});

describe("Saved web port", () => {
  it("shows the bound and saved ports and states that a change applies on the next launch", async () => {
    await openMcp();
    const port = panel("Web port");
    expect(await within(port).findByText(/This server listens on port 8765/)).toBeInTheDocument();
    expect(within(port).getByText(/No port is saved/)).toBeInTheDocument();
    expect(within(port).getByText(/applies on the next launch/i)).toBeInTheDocument();
  });

  it("saves a port and keeps the next-launch notice", async () => {
    const { user, server } = await openMcp();
    const port = panel("Web port");
    await user.type(await within(port).findByRole("spinbutton", { name: "Port for the next launch" }), "9000");
    await user.click(within(port).getByRole("button", { name: "Save port" }));
    expect(await within(port).findByText(/Saved port: 9000/)).toBeInTheDocument();
    expect(within(port).getByText(/applies on the next launch/i)).toBeInTheDocument();
    expect(within(port).getByText(/still listens on port 8765/i)).toBeInTheDocument();
    expect(server.find("PUT", "/v1/settings/web-port")[0]?.body).toEqual({ port: 9000 });
  });

  it("refuses a port outside 1024 to 65535 without calling the server", async () => {
    const { user, server } = await openMcp();
    const port = panel("Web port");
    const input = await within(port).findByRole("spinbutton", { name: "Port for the next launch" });
    await user.type(input, "80");
    await user.click(within(port).getByRole("button", { name: "Save port" }));
    expect(within(port).getByText("Enter a whole number from 1024 to 65535.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Enter a whole number/);
    expect(server.find("PUT", "/v1/settings/web-port")).toHaveLength(0);
  });

  it("clears the saved port with null", async () => {
    const routes = mcpRoutes();
    const { user, server } = await openMcp(routes);
    const port = panel("Web port");
    await user.type(await within(port).findByRole("spinbutton", { name: "Port for the next launch" }), "9000");
    await user.click(within(port).getByRole("button", { name: "Save port" }));
    await within(port).findByText(/Saved port: 9000/);
    await user.click(within(port).getByRole("button", { name: "Clear saved port" }));
    expect(await within(port).findByText(/No port is saved/)).toBeInTheDocument();
    expect(server.find("PUT", "/v1/settings/web-port").at(-1)?.body).toEqual({ port: null });
  });
});
