/**
 * Canvas state across the whole workspace: view changes and theme changes
 * must keep the draft, the node selection and the submitted run identity.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { FakeEventSource } from "../runs/test/fakes";
import { fakeServer } from "./test/fakeServer";
import { addWithKeyboard, inspector, outline, runPanel } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";

beforeAll(mockReactFlow);

let server: ReturnType<typeof fakeServer>;

beforeEach(() => {
  server = fakeServer();
  vi.stubGlobal("fetch", server.fetchImpl);
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => vi.unstubAllGlobals());

function nav() {
  return screen.getByRole("navigation", { name: "Workspace" });
}

function outlineNode(id: string) {
  return within(outline()).getByRole("button", { name: new RegExp(`^Node ${id} `) });
}

async function submitRun(user: ReturnType<typeof userEvent.setup>) {
  await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
  await user.click(within(inspector()).getByRole("checkbox", { name: "Use input query as a graph input" }));
  await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
  await waitFor(() => expect(runPanel()).toHaveTextContent("The draft matches revision 1."));
  await user.type(within(runPanel()).getByLabelText("Input query"), "What is RRF?");
  await user.click(within(runPanel()).getByRole("button", { name: "Run" }));
  const submitted = within(runPanel()).getByRole("region", { name: "Submitted run" });
  await waitFor(() => expect(submitted).toHaveTextContent("Run run1: queued"));
}

describe("canvas state across the workspace", () => {
  it("keeps the selected node and the submitted run after Canvas, Runs, Canvas", async () => {
    const user = userEvent.setup();
    render(<App />);
    await submitRun(user);
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    await user.click(outlineNode("prepare_query"));
    expect(outlineNode("prepare_query")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("rerank")).toHaveAttribute("aria-pressed", "false");

    await user.click(within(nav()).getByRole("link", { name: "Runs" }));
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Graph outline" })).toBeNull();
    await user.click(within(nav()).getByRole("link", { name: "Canvas" }));

    expect(await within(outline()).findByRole("button", { name: /^Node rerank / })).toBeInTheDocument();
    expect(outlineNode("prepare_query")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("rerank")).toHaveAttribute("aria-pressed", "false");
    const submitted = within(runPanel()).getByRole("region", { name: "Submitted run" });
    expect(submitted).toHaveTextContent("Run run1");
    expect(submitted).toHaveTextContent("Revision 1");
    expect(runPanel()).toHaveTextContent("The draft differs from revision 1.");
  });

  it("keeps canvas edits and the selection when the theme changes", async () => {
    const user = userEvent.setup();
    render(<App />);
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    await user.click(outlineNode("dense"));

    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme" }), "light");
    expect(document.documentElement.dataset.theme).toBe("light");

    expect(outlineNode("dense")).toHaveAttribute("aria-pressed", "true");
    expect(outlineNode("rerank")).toHaveAttribute("aria-pressed", "false");
    expect(within(inspector()).getByRole("button", { name: "Remove node" })).toBeInTheDocument();
  });
});
