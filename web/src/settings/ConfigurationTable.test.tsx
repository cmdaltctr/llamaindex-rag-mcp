import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { documentsServer } from "../test/fakeDocumentsServer";
import { renderWithProviders } from "../test/providers";
import { ConfigurationTable } from "./ConfigurationTable";
import type { ConfigurationSetting } from "./configurationTypes";

const IDENTITY = "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.";

const EMBED_MODEL: ConfigurationSetting = {
  key: "embed_model",
  value: "nomic-embed-text",
  source: "default",
  applies: "restart",
  restart_pending: false,
  saved: null,
  editable: false,
  read_only_reason: IDENTITY,
  kind: "text",
  choices: null,
  min: null,
  max: null,
  nullable: false,
};

function table() {
  const server = documentsServer({});
  renderWithProviders(
    <ConfigurationTable title="General" settings={[EMBED_MODEL]} revision="r1" editing={false} onEdit={vi.fn()} onClose={vi.fn()} onDirty={vi.fn()} onRestart={vi.fn()} />,
    { fetchImpl: server.fetchImpl },
  );
  return { user: userEvent.setup(), lock: within(screen.getByRole("table", { name: "General" })).getByRole("img", { name: IDENTITY }) };
}

describe("The lock on a read-only row", () => {
  it("explains on hover that the setting is read-only here, and why", async () => {
    const { user, lock } = table();
    await user.hover(lock);
    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent("Read-only on this page.");
    expect(tip).toHaveTextContent(IDENTITY);
  });

  it("shows the same explanation when the lock gets keyboard focus", async () => {
    const { user, lock } = table();
    // The first stop is the table's scroll area, which the Table primitive makes focusable.
    await user.tab();
    await user.tab();
    expect(lock).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Read-only on this page.");
  });
});
