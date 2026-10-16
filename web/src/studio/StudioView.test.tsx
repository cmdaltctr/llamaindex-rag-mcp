import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { PREFERENCES_KEY } from "../lib/preferences";
import { readDraft } from "./storage";
import { choose, edgeNames, openAllSections, openSections, outline, TEMPLATE_PIPELINE, TEMPLATE_REVISION, TEMPLATES } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const card = (name: string) => screen.getByRole("group", { name });

describe("Studio gallery", () => {
  it("shows the template, preset and saved pipeline cards", async () => {
    openStudio("#/studio", { templates: TEMPLATES, pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    expect(screen.getByRole("heading", { level: 1, name: "Studio" })).toBeInTheDocument();
    for (const title of ["Ingest sources", "Search", "Answer", "Empty pipeline", "Documents search", "Codebase search", "Search copy"]) {
      expect(await screen.findByRole("group", { name: title })).toBeInTheDocument();
    }
    expect(within(card("Documents search")).getByText("documents")).toBeInTheDocument();
    expect(within(card("Codebase search")).getByText("codebase")).toBeInTheDocument();
    expect(within(card("Search")).getByText(/Reproduces Engine.search/)).toBeInTheDocument();
    const open = within(card("Search copy")).getByRole("link", { name: "Open pipeline" });
    expect(open).toHaveAttribute("href", "#/studio/p1");
  });

  it("states that no pipeline is saved yet", async () => {
    openStudio("#/studio", { templates: TEMPLATES });
    expect(await screen.findByText(/No saved pipelines yet/)).toBeInTheDocument();
  });

  it("shows one friendly line when the templates cannot load and keeps the empty start", async () => {
    openStudio("#/studio", { templates: TEMPLATES, failures: { "GET /v1/pipeline-templates": 500 } });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(within(alert).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(card("Empty pipeline")).getByRole("button", { name: "Create pipeline" })).toBeEnabled();
    expect(within(card("Documents search")).getByRole("button", { name: "Create pipeline" })).toBeDisabled();
  });
});

describe("creating from a card", () => {
  it("creates the pipeline with a title only, seeds the draft for its id and opens the canvas", async () => {
    const { server, user } = openStudio("#/studio", { templates: TEMPLATES });
    await user.click(await within(await screen.findByRole("group", { name: "Search" })).findByRole("button", { name: "Create pipeline" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
    expect(server.last("POST", "/v1/pipelines")?.body).toEqual({ title: "Search", layout: { title: "Search" } });
    expect(server.calls.some((call) => call.path.endsWith("/revisions"))).toBe(false);
    expect(readDraft("pnew")?.graph.edges).toHaveLength(3);

    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    expect(edgeNames()).toHaveLength(3);
    expect(screen.getByRole("heading", { level: 1, name: "Search" })).toBeInTheDocument();
  });

  it("still opens the seeded graph when browser storage is blocked", async () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("blocked");
      });
    }
    const { user } = openStudio("#/studio", { templates: TEMPLATES });
    await user.click(await within(await screen.findByRole("group", { name: "Search" })).findByRole("button", { name: "Create pipeline" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    expect(edgeNames()).toHaveLength(3);
  });

  it("starts an empty graph from the empty card", async () => {
    const { user } = openStudio("#/studio", { templates: TEMPLATES });
    await user.click(within(await screen.findByRole("group", { name: "Empty pipeline" })).getByRole("button", { name: "Create pipeline" }));
    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(/graph is empty/);
  });

  it("seeds the documents preset from the search template with rerank on and the chosen collection", async () => {
    const collections = [
      { name: "papers", document_count: 3, chunk_count: 30, profile: "documents", display_name: null, store: { name: "lancedb", label: "LanceDB" } },
      { name: "src", document_count: 5, chunk_count: 90, profile: "codebase", display_name: null, store: { name: "lancedb", label: "LanceDB" } },
    ];
    const { server, user } = openStudio("#/studio", { templates: TEMPLATES, collections });
    const documents = await screen.findByRole("group", { name: "Documents search" });
    await choose(user, within(documents).getByLabelText("Collection"), "papers");
    await user.click(within(documents).getByRole("button", { name: "Create pipeline" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
    expect(server.last("POST", "/v1/pipelines")?.body).toEqual({ title: "Documents search", layout: { title: "Documents search" } });
    const draft = readDraft("pnew");
    expect(draft?.graph.profile).toBe("documents");
    expect(draft?.graph.collection).toBe("papers");
    expect(draft?.graph.nodes.find((node) => node.operation === "select.rerank")?.params).toEqual({ enabled: true });

    // The canvas opens with that graph, ready to save as the first revision.
    await openSections(user, "Pipeline settings");
    expect(await screen.findByLabelText("Collection")).toHaveValue("papers");
    expect(screen.getByLabelText("Profile")).toHaveTextContent("documents");
  });

  it("seeds the codebase preset with rerank off, keeping the node in the graph", async () => {
    const { user } = openStudio("#/studio", { templates: TEMPLATES });
    const codebase = await screen.findByRole("group", { name: "Codebase search" });
    await user.click(within(codebase).getByRole("button", { name: "Create pipeline" }));
    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
    const draft = readDraft("pnew");
    expect(draft?.graph.profile).toBe("codebase");
    expect(draft?.graph.collection).toBeNull();
    expect(draft?.graph.nodes.map((node) => node.id)).toEqual(["prepare", "dense", "rerank", "select"]);
    expect(draft?.graph.nodes.find((node) => node.id === "rerank")?.params).toEqual({ enabled: false });
  });

  it("pre-fills the collection the user last worked with when the server still lists it", async () => {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ theme: "system", lastCollection: "src" }));
    const collections = [{ name: "src", document_count: 5, chunk_count: 90, profile: "codebase", display_name: null, store: { name: "lancedb", label: "LanceDB" } }];
    openStudio("#/studio", { templates: TEMPLATES, collections });
    const codebase = await screen.findByRole("group", { name: "Codebase search" });
    await waitFor(() => expect(within(codebase).getByLabelText("Collection")).toHaveTextContent("src"));
  });

  it("shows one friendly line with Retry when the server refuses, and stays on the gallery", async () => {
    const { server, user } = openStudio("#/studio", { templates: TEMPLATES, failures: { "POST /v1/pipelines": 500 } });
    await user.click(within(await screen.findByRole("group", { name: "Answer" })).getByRole("button", { name: "Create pipeline" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(window.location.hash).toBe("#/studio");

    delete server.failures["POST /v1/pipelines"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(window.location.hash).toBe("#/studio/pnew"));
  });
});

describe("saved pipelines", () => {
  it("opens a saved pipeline at its latest revision with validate and run offered", async () => {
    const { user } = openStudio("#/studio/p1", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    expect(screen.getByRole("heading", { level: 1, name: "Search copy" })).toBeInTheDocument();
    expect(outline()).toBeInTheDocument();
    const panel = screen.getByRole("region", { name: "Revision and run" });
    expect(panel).toHaveTextContent("The draft matches revision 1.");
    expect(within(panel).getByRole("button", { name: "Validate" })).toBeEnabled();
    expect(within(panel).getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("shows not found, with a way back, for a pipeline the server does not return", async () => {
    openStudio("#/studio/missing", { pipelines: [TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] });
    expect(await screen.findByText(/The pipeline "missing" could not be found/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Studio" })).toHaveAttribute("href", "#/studio");
  });
});
