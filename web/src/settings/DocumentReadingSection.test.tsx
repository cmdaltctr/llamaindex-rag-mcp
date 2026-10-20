import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentReadingState } from "../api/settingsDocumentReading";
import { json } from "../test/fakeDocumentsServer";
import { startApp } from "../test/startApp";
import { readingState, settingsServer } from "./test/fixtures";

const RESTART_NOTE = "These settings apply after a restart of omrg web. Saving does not change the reading in force.";
const IDENTITY_NOTE = "These settings are part of the index identity. After a restart, the next ingest can read existing files again.";

async function openSection(handlers = {}) {
  const server = settingsServer(handlers);
  startApp("#/settings/document-reading", server);
  const section = await screen.findByRole("region", { name: "Document reading" });
  await within(section).findByRole("group", { name: "PDF reader" });
  return { server, section, user: userEvent.setup() };
}

function row(name: string) {
  return screen.getByRole("group", { name });
}

/** A fake server that holds the state and applies each PUT, as the real route does. */
function savingServer(start: DocumentReadingState) {
  let state = start;
  return {
    "GET /v1/settings/document-reading": () => state,
    "PUT /v1/settings/document-reading": (body: Record<string, unknown>) => {
      const values = body.values as Record<string, unknown>;
      state = {
        ...state,
        revision: "r2",
        settings: state.settings.map((setting) => {
          if (!(setting.key in values)) return setting;
          const saved = values[setting.key] as DocumentReadingState["settings"][number]["saved"];
          return { ...setting, saved, restart_pending: saved !== null && saved !== setting.value };
        }),
      };
      return state;
    },
  };
}

describe("Document reading", () => {
  it("opens from its address with its chip selected, straight before Configuration", async () => {
    await openSection();
    const chips = within(screen.getByRole("group", { name: "Sections" })).getAllByRole("button").map((button) => button.textContent);
    expect(chips.indexOf("Document reading")).toBe(chips.indexOf("Configuration") - 1);
    expect(screen.getByRole("button", { name: "Document reading" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows one row for each of the nine keys with the value in force, its source and the default", async () => {
    const { section } = await openSection();
    const names = ["PDF reader", "OCR fallback", "Lowest text confidence", "OCR page fraction", "OCR routing unit", "Primary engine", "Fallback engine", "Maths routing", "Maths page fraction"];
    for (const name of names) expect(within(section).getByRole("group", { name })).toBeInTheDocument();
    const reader = row("PDF reader");
    expect(within(reader).getByText("pdf_inspector", { selector: "code" })).toBeInTheDocument();
    expect(reader).toHaveTextContent("Default: pdf_inspector");
    expect(within(row("OCR fallback")).getByText("On", { selector: "code" })).toBeInTheDocument();
    expect(within(row("OCR page fraction")).getByText("0.1", { selector: "code" })).toBeInTheDocument();
    expect(row("OCR page fraction")).toHaveTextContent("default");
    expect(within(section).queryByText("Restart to apply")).toBeNull();
  });

  it("says the settings apply after a restart, that they are part of the index identity, and that a pipeline step can choose its reader", async () => {
    const { section } = await openSection();
    expect(section).toHaveTextContent(RESTART_NOTE);
    expect(section).toHaveTextContent(IDENTITY_NOTE);
    expect(section).toHaveTextContent("A Read document step in a pipeline can choose its own reader.");
  });

  it("shows a value saved but not yet in force with Restart to apply", async () => {
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ pdf_reader: { value: "auto", saved: "liteparse", source: "config-file", restart_pending: true } }, { pdf_reader_in_use: "liteparse" }),
    });
    const reader = row("PDF reader");
    expect(within(reader).getByText("auto", { selector: "code" })).toBeInTheDocument();
    expect(reader).toHaveTextContent("Saved for the next launch: liteparse");
    expect(within(reader).getByText("Restart to apply")).toBeInTheDocument();
    expect(reader).toHaveTextContent("In use: liteparse");
  });

  it("says nothing about the reader in use when it is the configured one", async () => {
    await openSection();
    expect(row("PDF reader")).not.toHaveTextContent("In use:");
  });

  it("makes a key from the environment read-only and names its variable", async () => {
    const lock = "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here.";
    await openSection({
      "GET /v1/settings/document-reading": () => readingState({ ocr_routing_unit: { value: "page", source: "dotenv", locked: true, lock_reason: lock } }),
    });
    const unit = row("OCR routing unit");
    expect(within(unit).queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(unit).toHaveTextContent(lock);
    expect(within(row("PDF reader")).getByRole("button", { name: "Edit PDF reader" })).toBeInTheDocument();
  });

  it("marks a PDF reader that is not installed and does not let it be chosen", async () => {
    const { user } = await openSection();
    await user.click(within(row("PDF reader")).getByRole("button", { name: "Edit PDF reader" }));
    expect(row("PDF reader")).toHaveTextContent("pypdfium2 is not available. The package 'pypdfium2' is not installed.");
    await user.click(within(row("PDF reader")).getByRole("combobox", { name: "PDF reader" }));
    expect(await screen.findByRole("option", { name: "pypdfium2 (not installed)" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("option", { name: "liteparse" })).not.toHaveAttribute("aria-disabled");
  });

  it("lists the engines the server reports and allows one that is not provisioned, with the reason", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    const fallback = row("Fallback engine");
    expect(fallback).toHaveTextContent("Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl.");
    await user.click(within(row("Primary engine")).getByRole("button", { name: "Edit Primary engine" }));
    await user.click(within(row("Primary engine")).getByRole("combobox", { name: "Primary engine" }));
    const options = await screen.findAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["dots-mocr", "paddleocr-vl (not provisioned)"]);
    await user.click(screen.getByRole("option", { name: "paddleocr-vl (not provisioned)" }));
    expect(row("Primary engine")).toHaveTextContent("Not provisioned. Run python3 ocr-workers/provision.py paddleocr-vl.");
    await user.click(within(row("Primary engine")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_engine_primary: "paddleocr-vl" }, revision: "r1" }]));
  });

  it("says when OCR_WORKER_COMMAND replaces the primary engine", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({}, { ocr: { ...readingState().ocr, worker_command_set: true } }) });
    expect(row("Primary engine")).toHaveTextContent("OCR_WORKER_COMMAND is set, so it replaces the primary engine.");
    expect(row("Fallback engine")).not.toHaveTextContent("OCR_WORKER_COMMAND");
  });

  it("shows a saved empty fallback engine as no fallback", async () => {
    await openSection({ "GET /v1/settings/document-reading": () => readingState({ ocr_engine_fallback: { value: "", saved: "", source: "config-file" } }) });
    expect(within(row("Fallback engine")).getByText("None (no fallback)")).toBeInTheDocument();
  });

  it("saves a fraction with the revision, shows Restart to apply and opens the restart dialog with the index identity note", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("OCR page fraction")).getByRole("button", { name: "Edit OCR page fraction" }));
    const input = within(row("OCR page fraction")).getByRole("spinbutton", { name: "OCR page fraction" });
    expect(input).toHaveValue(0.1);
    await user.clear(input);
    await user.type(input, "0.2");
    await user.click(within(row("OCR page fraction")).getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Restart to apply?" });
    expect(dialog).toHaveTextContent("OCR page fraction applies after a restart.");
    expect(dialog).toHaveTextContent(IDENTITY_NOTE);
    expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_fallback_page_fraction: 0.2 }, revision: "r1" }]);
    await user.click(within(dialog).getByRole("button", { name: "Later" }));
    const fraction = row("OCR page fraction");
    expect(within(fraction).getByText("Restart to apply")).toBeInTheDocument();
    expect(fraction).toHaveTextContent("Saved for the next launch: 0.2");
    expect(within(fraction).getByText("0.1", { selector: "code" })).toBeInTheDocument();
  });

  it("refuses a fraction outside 0 to 1 before it sends anything", async () => {
    const { user, server } = await openSection();
    await user.click(within(row("Maths page fraction")).getByRole("button", { name: "Edit Maths page fraction" }));
    const input = within(row("Maths page fraction")).getByRole("spinbutton", { name: "Maths page fraction" });
    await user.clear(input);
    await user.type(input, "1.5");
    await user.click(within(row("Maths page fraction")).getByRole("button", { name: "Save" }));
    expect(row("Maths page fraction")).toHaveTextContent("Enter a number from 0 to 1.");
    expect(server.find("PUT", "/v1/settings/document-reading")).toHaveLength(0);
  });

  it("saves a switch as true or false", async () => {
    const { user, server } = await openSection(savingServer(readingState()));
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Edit Maths routing" }));
    const toggle = within(row("Maths routing")).getByRole("switch", { name: "Maths routing" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await user.click(within(row("Maths routing")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_maths_routing_enabled: false }, revision: "r1" }]));
  });

  it("sends null for Use default, so the key leaves omrg.jsonc", async () => {
    const { user, server } = await openSection(savingServer(readingState({ ocr_engine_fallback: { value: "paddleocr-vl", saved: "my-engine", source: "default", restart_pending: true } }, { ocr: { ...readingState().ocr, engines: [...readingState().ocr.engines, { name: "my-engine", available: false, reason: "Not provisioned. Run python3 ocr-workers/provision.py my-engine." }] } })));
    await user.click(within(row("Fallback engine")).getByRole("button", { name: "Edit Fallback engine" }));
    await user.click(within(row("Fallback engine")).getByRole("button", { name: "Use default" }));
    await waitFor(() => expect(server.find("PUT", "/v1/settings/document-reading").map((call) => call.body)).toEqual([{ values: { ocr_engine_fallback: null }, revision: "r1" }]));
    await waitFor(() => expect(within(row("Fallback engine")).queryByText("Restart to apply")).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers no Use default for a key the file does not hold", async () => {
    const { user } = await openSection();
    await user.click(within(row("OCR routing unit")).getByRole("button", { name: "Edit OCR routing unit" }));
    expect(within(row("OCR routing unit")).queryByRole("button", { name: "Use default" })).toBeNull();
  });

  it("shows the server message of a refused save and leaves the row unchanged", async () => {
    const { user } = await openSection({
      "PUT /v1/settings/document-reading": () => json({ status: "error", message: "pdf_reader: This PDF reader is not installed. Install its package, then save again." }, 400),
    });
    await user.click(within(row("PDF reader")).getByRole("button", { name: "Edit PDF reader" }));
    await user.click(within(row("PDF reader")).getByRole("combobox", { name: "PDF reader" }));
    await user.click(await screen.findByRole("option", { name: "liteparse" }));
    await user.click(within(row("PDF reader")).getByRole("button", { name: "Save" }));
    expect(await within(row("PDF reader")).findByRole("alert")).toHaveTextContent("pdf_reader: This PDF reader is not installed. Install its package, then save again.");
    await user.click(within(row("PDF reader")).getByRole("button", { name: "Cancel" }));
    expect(within(row("PDF reader")).getByText("pdf_inspector", { selector: "code" })).toBeInTheDocument();
    expect(row("PDF reader")).not.toHaveTextContent("Restart to apply");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers Reload after a file conflict and reads the section again", async () => {
    const { user, server } = await openSection({
      "PUT /v1/settings/document-reading": () => json({ status: "error", message: "omrg.jsonc changed on disk. Reload to see the new values." }, 409),
    });
    await user.click(within(row("OCR routing unit")).getByRole("button", { name: "Edit OCR routing unit" }));
    await user.click(within(row("OCR routing unit")).getByRole("combobox", { name: "OCR routing unit" }));
    await user.click(await screen.findByRole("option", { name: "page" }));
    await user.click(within(row("OCR routing unit")).getByRole("button", { name: "Save" }));
    const alert = await within(row("OCR routing unit")).findByRole("alert");
    expect(alert).toHaveTextContent("omrg.jsonc changed on disk. Reload to see the new values.");
    expect(server.find("GET", "/v1/settings/document-reading")).toHaveLength(1);
    await user.click(within(alert).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(server.find("GET", "/v1/settings/document-reading")).toHaveLength(2));
  });

  it("shows one friendly line with Retry when the section cannot load", async () => {
    const server = settingsServer({ "GET /v1/settings/document-reading": () => json({ status: "error", message: "Traceback boom" }, 500) });
    startApp("#/settings/document-reading", server);
    const section = await screen.findByRole("region", { name: "Document reading" });
    expect(await within(section).findByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByText(/Traceback/)).toBeNull();
  });
});
