import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { documentsServer, json } from "../../test/fakeDocumentsServer";
import { renderWithProviders } from "../../test/providers";
import { OpenFullOutput, OutputCut } from "./OutputViewer";

const SECRET = "sk-live-abcdef1234567890"; // gitleaks:allow (fake key: the redaction tests need a key-shaped value)

let downloads: { name: string; text: Promise<string>; url: string }[] = [];
let revoked: string[] = [];

beforeEach(() => {
  downloads = [];
  revoked = [];
  let next = 0;
  const blobs = new Map<string, Blob>();
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
    const url = `blob:test/${++next}`;
    blobs.set(url, blob as Blob);
    return url;
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation((url) => void revoked.push(url));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    downloads.push({ name: this.download, text: blobs.get(this.href)!.text(), url: this.href });
  });
});

afterEach(() => vi.restoreAllMocks());

function open(ui: React.ReactElement, handlers = {}) {
  const server = documentsServer(handlers);
  renderWithProviders(ui, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

describe("output viewer", () => {
  it("shows a value from memory as plain JSON text, masked, and never as markup", async () => {
    const value = { text: "<b>bold</b><script>alert(1)</script>", api_key: SECRET, url: `https://u:${SECRET}@h/x` };
    const { user, server } = open(<OpenFullOutput runId="r1" name="evidence-row-1" source={{ value }} />);
    await user.click(screen.getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    const pre = dialog.querySelector("pre")!;
    expect(pre.textContent).toContain('"text": "<b>bold</b><script>alert(1)</script>"');
    expect(dialog.querySelector("b, script")).toBeNull();
    expect(dialog.textContent).not.toContain(SECRET);
    expect(pre.textContent).toContain('"api_key": "[redacted]"');
    expect(dialog).toHaveTextContent("The whole value is shown.");
    expect(server.calls).toHaveLength(0);
  });

  it("states the cut above 256 KiB and downloads the whole value, then revokes the address", async () => {
    const value = { text: "y".repeat(300 * 1024) };
    const { user } = open(<OpenFullOutput runId="r1" name="node-dense-summary" source={{ value }} />);
    await user.click(screen.getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(dialog).toHaveTextContent("The value is 301 KiB. Only the first 256 KiB are shown. Download it to read the rest.");
    expect(new TextEncoder().encode(dialog.querySelector("pre")!.textContent!).length).toBeLessThanOrEqual(256 * 1024);
    await user.click(within(dialog).getByRole("button", { name: "Download" }));
    expect(downloads).toHaveLength(1);
    expect(downloads[0]!.name).toBe("run-r1-node-dense-summary.json");
    expect(JSON.parse(await downloads[0]!.text)).toEqual(value);
    expect(revoked).toEqual([downloads[0]!.url]);
  });

  it("loads an artefact only when opened, from the artefact route", async () => {
    const { user, server } = open(<OpenFullOutput runId="r1" name="event-0a1b" source={{ artefact: "event-0a1b" }} />, {
      "GET /v1/runs/r1/artefacts/event-0a1b": () => ({ status: "ok", run_id: "r1", name: "event-0a1b", value: { message: "done", data: { rows: [1, 2] } } }),
    });
    expect(server.calls).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    expect(await within(dialog).findByText(/"message": "done"/)).toBeInTheDocument();
    expect(server.calls.map((call) => call.path)).toEqual(["/v1/runs/r1/artefacts/event-0a1b"]);
  });

  it("shows one friendly line with Retry when the artefact cannot be loaded", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let fail = true;
    const { user } = open(<OpenFullOutput runId="r1" name="event-0a1b" source={{ artefact: "event-0a1b" }} />, {
      "GET /v1/runs/r1/artefacts/event-0a1b": () => (fail ? json({ status: "error", message: "RAW /srv/artefacts/r1 boom" }, 500) : { status: "ok", value: "later" }),
    });
    await user.click(screen.getByRole("button", { name: "Open full output" }));
    const dialog = await screen.findByRole("dialog", { name: "Full output" });
    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(dialog.textContent).not.toContain("RAW");
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await within(dialog).findByText('"later"')).toBeInTheDocument();
  });
});

describe("cut notice", () => {
  it("offers the route for a summary the server cut in this run", () => {
    open(<OutputCut runId="r1" name="summary" value={{ message: "m", truncated: true, artefact_ref: "r1/event-0a1b.json" }} />);
    expect(screen.getByText("The server cut this output.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open full output" })).toBeInTheDocument();
  });

  it("states the cut without the action when the reference names another run", () => {
    open(<OutputCut runId="r1" name="summary" value={{ message: "m", truncated: true, artefact_ref: "r2/event-0a1b.json" }} />);
    expect(screen.getByText("The server cut this output. The full output belongs to another run, so it cannot be opened here.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("states the cut without the action when the reference to this run is not valid", () => {
    open(<OutputCut runId="r1" name="summary" value={{ message: "m", truncated: true, artefact_ref: "r1/../x.json" }} />);
    expect(screen.getByText("The server cut this output. Its reference to the full output is not valid, so it cannot be opened here.")).toBeInTheDocument();
    expect(screen.queryByText(/belongs to another run/)).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers the value from memory when the preview cuts it, and nothing when nothing is cut", () => {
    const { server } = open(
      <>
        <OutputCut runId="r1" name="long" value={{ text: "x".repeat(5000) }} />
        <OutputCut runId="r1" name="short" value={{ text: "short" }} />
      </>,
    );
    expect(screen.getAllByText("Part of this output is not shown here.")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Open full output" })).toHaveLength(1);
    expect(server.calls).toHaveLength(0);
  });
});
