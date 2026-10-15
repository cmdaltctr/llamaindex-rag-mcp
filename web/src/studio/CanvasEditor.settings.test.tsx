import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { json } from "./test/fakeServer";
import { addWithKeyboard, EMPTY_PIPELINE, inspector, outline, runPanel, savedDocument } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

async function setup(options: Parameters<typeof openStudio>[1] = {}) {
  const view = openStudio("#/studio/pnew", { pipelines: [EMPTY_PIPELINE], ...options });
  await screen.findByRole("region", { name: "Operation catalogue" });
  await within(screen.getByRole("region", { name: "Operation catalogue" })).findByRole("button", { name: /retrieve\.dense/ });
  return view;
}

function group(name: string) {
  return within(inspector()).getByRole("group", { name });
}

async function saveRevision(user: Awaited<ReturnType<typeof setup>>["user"], server: Awaited<ReturnType<typeof setup>>["server"]) {
  const before = server.calls.length;
  await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
  await waitFor(() => expect(server.calls.slice(before).some((c) => c.path.endsWith("/revisions") && c.method === "POST")).toBe(true));
  return savedDocument([...server.calls].reverse().find((c) => c.path.endsWith("/revisions") && c.method === "POST"));
}

const ADMITTED_CONTROLS = {
  status: "ok",
  valid: true,
  admitted: true,
  order: ["prepare_query", "rerank"],
  nodes: [
    {
      node_id: "rerank",
      controls: [{ lever: "retrieval.rerank_enabled", value: false, source: "profile", detail: "documents profile" }],
    },
  ],
};

describe("node controls", () => {
  it("writes Inherit, On and Off for a lever and shows the effective inherited value", async () => {
    const { server, user } = await setup({ validate: (body) => (body.inputs ? json(ADMITTED_CONTROLS) : undefined) as Response });
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await user.click(within(inspector()).getByRole("checkbox", { name: "Use input query as a graph input" }));
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");

    expect(within(group("Enabled")).getByRole("radio", { name: "Inherit" })).toBeChecked();
    expect(group("Enabled")).toHaveTextContent(/Validate with run inputs to see the effective value/);

    await user.type(within(runPanel()).getByLabelText("Input query"), "What is RRF?");
    await user.click(within(runPanel()).getByRole("button", { name: "Validate" }));
    await waitFor(() => expect(group("Enabled")).toHaveTextContent("Effective value: Off (profile: documents profile)"));
    expect(server.last("POST", "/v1/pipelines/validate")?.body).toMatchObject({ inputs: { query: "What is RRF?" } });

    await user.click(within(group("Enabled")).getByRole("radio", { name: "Off" }));
    expect((await saveRevision(user, server)).nodes.find((n) => n.id === "rerank")?.params).toEqual({ enabled: false });
    await user.click(within(group("Enabled")).getByRole("radio", { name: "On" }));
    expect((await saveRevision(user, server)).nodes.find((n) => n.id === "rerank")?.params).toEqual({ enabled: true });
    await user.click(within(group("Enabled")).getByRole("radio", { name: "Inherit" }));
    expect((await saveRevision(user, server)).nodes.find((n) => n.id === "rerank")).not.toHaveProperty("params");
  });

  it("refuses values outside the parameter schema", async () => {
    const { server, user } = await setup();
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await user.click(within(group("Top K")).getByRole("radio", { name: "Set value" }));
    const field = within(group("Top K")).getByLabelText("Top K value");
    await user.type(field, "0");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(group("Top K")).toHaveTextContent("Enter a value of at least 1.");
    expect((await saveRevision(user, server)).nodes[0]).not.toHaveProperty("params");

    await user.clear(field);
    await user.type(field, "8");
    expect(field).toHaveAttribute("aria-invalid", "false");
    expect((await saveRevision(user, server)).nodes[0]?.params).toEqual({ top_k: 8 });
  });

  it("offers a bypass only when the operation declares one", async () => {
    const { server, user } = await setup();
    await addWithKeyboard(user, "Threshold and top-k", "select.threshold");
    expect(within(inspector()).queryByRole("checkbox", { name: "Bypass this node" })).not.toBeInTheDocument();
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    await user.click(within(inspector()).getByRole("checkbox", { name: "Bypass this node" }));
    expect((await saveRevision(user, server)).nodes.find((n) => n.id === "rerank")?.enabled).toBe(false);
  });
});

describe("revision, run and cancellation", () => {
  it("runs the saved revision and keeps the admitted snapshot after later draft edits", async () => {
    const { server, user } = await setup();
    await addWithKeyboard(user, "Prepare query", "retrieve.prepare_query");
    await user.click(within(inspector()).getByRole("checkbox", { name: "Use input query as a graph input" }));
    await addWithKeyboard(user, "Cross-encoder rerank", "select.rerank");
    expect(within(runPanel()).getByRole("button", { name: "Run" })).toBeDisabled();
    expect(runPanel()).toHaveTextContent("Save a revision before you run.");

    await user.click(within(group("Enabled")).getByRole("radio", { name: "On" }));
    await saveRevision(user, server);
    await waitFor(() => expect(runPanel()).toHaveTextContent("The draft matches revision 1."));
    // An unsaved edit before submission: Run must still submit revision 1 as saved.
    await user.click(within(group("Enabled")).getByRole("radio", { name: "Off" }));
    expect(runPanel()).toHaveTextContent("The draft differs from revision 1.");
    await user.type(within(runPanel()).getByLabelText("Input query"), "What is RRF?");
    await user.click(within(runPanel()).getByRole("button", { name: "Run" }));

    await waitFor(() => expect(server.last("POST", "/v1/runs")).toBeDefined());
    expect(server.last("POST", "/v1/runs")?.body).toEqual({ revision_id: "pnew-r1", inputs: { query: "What is RRF?" } });
    const submitted = await within(runPanel()).findByRole("region", { name: "Latest run" });
    await waitFor(() => expect(submitted).toHaveTextContent("queued"));
    expect(submitted).toHaveTextContent("Revision 1");
    await waitFor(() => expect(submitted).toHaveTextContent('"enabled": true'));
    expect(submitted).not.toHaveTextContent('"enabled": false');

    // Edits after submission change the draft only.
    await user.click(within(group("Enabled")).getByRole("radio", { name: "Inherit" }));
    await user.click(within(outline()).getByRole("button", { name: /^Node prepare_query/ }));
    await user.click(within(inspector()).getByRole("button", { name: "Remove node" }));
    expect(runPanel()).toHaveTextContent("The draft differs from revision 1.");
    expect(submitted).toHaveTextContent('"enabled": true');
    expect(submitted).not.toHaveTextContent('"enabled": false');
    expect(submitted).toHaveTextContent("prepare_query");

    await user.click(within(runPanel()).getByRole("button", { name: "Cancel run" }));
    await waitFor(() => expect(submitted).toHaveTextContent("cancelling"));
    expect(server.last("POST", "/v1/runs/run1/cancel")).toBeDefined();
  });

  it("saves the layout without creating a revision", async () => {
    const { server, user } = await setup();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save layout" }));
    await waitFor(() => expect(server.last("PUT", "/v1/pipelines/pnew/layout")).toBeDefined());
    expect(server.calls.some((c) => c.path.endsWith("/revisions") && c.method === "POST")).toBe(false);
    expect(await screen.findByText(/Layout saved/)).toBeInTheDocument();
  });

  it("never changes a collection's profile when a layout or a revision is saved", async () => {
    const { server, user } = await setup();
    await addWithKeyboard(user, "Dense retrieval", "retrieve.dense");
    await user.click(within(runPanel()).getByRole("button", { name: "Save layout" }));
    await waitFor(() => expect(server.last("PUT", "/v1/pipelines/pnew/layout")).toBeDefined());
    await user.click(within(runPanel()).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(server.last("POST", "/v1/pipelines/pnew/revisions")).toBeDefined());
    const profileCalls = server.calls.filter((call) => /\/collections\/[^/]+\/profile/.test(call.path));
    expect(profileCalls).toEqual([]);
    expect(server.calls.filter((call) => call.method === "PATCH")).toEqual([]);
  });
});
