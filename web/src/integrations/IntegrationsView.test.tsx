import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Integration } from "../api/integrations";
import { documentsServer, json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";

const EXTRAS: Array<[string, string, Integration["availability"]]> = [
  ["chroma", "Chroma vector store", "not-installed"],
  ["hybrid", "Hybrid search", "available"],
  ["pdf-pypdfium2", "PDF reader: pypdfium2", "available"],
  ["pdf-inspector", "PDF reader: pdf-inspector", "available"],
  ["community-leiden", "Leiden communities", "not-installed"],
  ["azure", "Azure Document Intelligence", "not-installed"],
  ["llamacpp", "llama.cpp provider", "unknown"],
  ["openrouter", "OpenRouter provider", "available"],
  ["torch", "PyTorch reranker", "not-installed"],
  ["web", "Local web workspace", "available"],
];

const CATALOGUE: Integration[] = [
  ...EXTRAS.map(([id, name, availability]) => ({
    id,
    name,
    purpose: `Purpose of ${id}.`,
    extra: id,
    install_command: `uv sync --extra ${id}`,
    pip_command: `pip install "omrs[${id}]"`,
    availability,
    installable: false,
    install_reason: "not-uv-tool" as const,
    packages: [],
    install_caution: null,
    base: ["pdf-inspector", "llamacpp", "openrouter"].includes(id),
  })),
  {
    id: "magika",
    name: "Magika file detection",
    purpose: "Detects file types.",
    extra: null,
    install_command: null,
    pip_command: null,
    availability: "available",
    installable: false,
    install_reason: "not-installable-here",
    packages: [],
    install_caution: null,
    base: true,
  },
];

const serve = (handler: () => unknown = () => ({ status: "ok", install_type: "checkout", integrations: CATALOGUE })) =>
  documentsServer({ "GET /v1/integrations": handler });

const card = async (name: string) => {
  const list = await screen.findByRole("list", { name: "Integrations" });
  const item = within(list).getAllByRole("listitem").find((entry) => within(entry).queryByRole("heading", { name }) !== null);
  if (item === undefined) throw new Error(`No card named ${name}`);
  return item;
};

afterEach(() => vi.restoreAllMocks());

describe("Integrations", () => {
  it("lists the whole catalogue in server order with name, purpose, status and command", async () => {
    startApp("#/integrations", serve());
    const list = await screen.findByRole("list", { name: "Integrations" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(11);
    const names = items.map((item) => within(item).getByRole("heading").textContent);
    expect(names).toEqual([...EXTRAS.map(([, name]) => name), "Magika file detection"]);
    expect(items[5]).toHaveTextContent("Purpose of azure.");
    expect(items[5]).toHaveTextContent("uv sync --extra azure");
    expect(screen.getByRole("heading", { level: 1, name: "Integrations" })).toBeInTheDocument();
  });

  it("places the cards in masonry columns, so a tall card leaves no gap beside short ones", async () => {
    startApp("#/integrations", serve());
    const list = await screen.findByRole("list", { name: "Integrations" });
    expect(within(list).getByTestId("masonry")).toBeInTheDocument();
    for (const item of within(list).getAllByRole("listitem")) expect(item.closest("[data-testid='masonry-column']")).not.toBeNull();
  });

  it("states installed, absent and unknown availability in text", async () => {
    startApp("#/integrations", serve());
    const badge = async (name: string) => within(await card(name)).getByText(/^(Installed|Not installed|Unknown)$/, { selector: "[data-slot=badge]" });
    expect(await badge("PDF reader: pdf-inspector")).toHaveTextContent("Installed");
    expect(await badge("Chroma vector store")).toHaveTextContent("Not installed");
    expect(await badge("llama.cpp provider")).toHaveTextContent("Unknown");
  });

  it("marks every base install entry with Base default next to its status, and no other entry", async () => {
    startApp("#/integrations", serve());
    const magika = await card("Magika file detection");
    expect(within(magika).getByText("Base default", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(await card("PDF reader: pdf-inspector")).getByText("Base default", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(within(await card("PDF reader: pypdfium2")).queryByText("Base default")).not.toBeInTheDocument();
    expect(within(await card("Chroma vector store")).queryByText("Base default")).not.toBeInTheDocument();
  });

  it("gives magika no install command and no copy button", async () => {
    startApp("#/integrations", serve());
    const magika = await card("Magika file detection");
    expect(within(magika).queryByRole("button")).not.toBeInTheDocument();
    expect(magika).not.toHaveTextContent(/uv sync|pip install/);
    expect(magika).toHaveTextContent(/always on/i);
  });

  it("writes the exact command to the clipboard and confirms it", async () => {
    const user = userEvent.setup();
    startApp("#/integrations", serve());
    const azure = await card("Azure Document Intelligence");
    await user.click(within(azure).getByRole("button", { name: "Copy install command for Azure Document Intelligence" }));
    expect(await navigator.clipboard.readText()).toBe("uv sync --extra azure");
    expect(await within(azure).findByRole("status")).toHaveTextContent("Copied");
  });

  it("keeps the command selectable and says so when the clipboard is missing", async () => {
    const user = userEvent.setup();
    startApp("#/integrations", serve());
    const azure = await card("Azure Document Intelligence");
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    await user.click(within(azure).getByRole("button", { name: /Copy install command/ }));
    expect(await within(azure).findByRole("status")).toHaveTextContent(/select the command/i);
    expect(within(azure).getByText("uv sync --extra azure")).toBeVisible();
  });

  it("keeps the command selectable and says so when the clipboard rejects", async () => {
    const user = userEvent.setup();
    startApp("#/integrations", serve());
    const azure = await card("Azure Document Intelligence");
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    await user.click(within(azure).getByRole("button", { name: /Copy install command/ }));
    expect(await within(azure).findByRole("status")).toHaveTextContent(/select the command/i);
    expect(within(azure).getByText("uv sync --extra azure")).toBeVisible();
  });

  it("explains that availability reflects this launch and that installing here needs the command outside the app", async () => {
    startApp("#/integrations", serve());
    await screen.findByRole("list", { name: "Integrations" });
    const notice = screen.getByRole("note");
    expect(notice).toHaveTextContent(/running launch/i);
    expect(notice).toHaveTextContent(/outside the app/i);
    expect(notice).toHaveTextContent(/restart the server/i);
    expect(notice).not.toHaveTextContent(/never installs/i);
  });

  it("offers no install or run control when the server cannot install", async () => {
    startApp("#/integrations", serve());
    await screen.findByRole("list", { name: "Integrations" });
    const labels = screen.getAllByRole("button").map((button) => button.getAttribute("aria-label") ?? button.textContent ?? "");
    const main = document.querySelector("main") as HTMLElement;
    const own = within(main).getAllByRole("button").map((button) => button.getAttribute("aria-label") ?? "");
    expect(own.every((label) => label.startsWith("Copy "))).toBe(true);
    expect(labels.some((label) => /^(install|run|download|update)\b/i.test(label))).toBe(false);
  });

  it("shows one friendly line with Retry and never the raw text when the listing fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    startApp(
      "#/integrations",
      serve(() => (fail ? json({ status: "error", message: "Probe <html>exploded" }, 500) : { status: "ok", install_type: "checkout", integrations: CATALOGUE })),
    );
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("exploded");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    fail = false;
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Integrations" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
