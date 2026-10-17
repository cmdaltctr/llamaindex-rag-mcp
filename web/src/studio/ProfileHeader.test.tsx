import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/providers";
import { ProfileHeader } from "./ProfileHeader";
import { CANVAS_INTRO, PURPOSE_LABELS, PURPOSE_LINES, READ_ONLY_NOTICE } from "./profileCopy";
import {
  addWithKeyboard,
  ANSWER_PIPELINE,
  ANSWER_REVISION,
  DOCUMENTS_PROFILE,
  EMPTY_PIPELINE,
  NOT_READY_PROFILE,
  openAllSections,
  outline,
  runPanel,
  TEMPLATE_PIPELINE,
  TEMPLATE_REVISION,
  USER_PROFILE,
} from "./test/helpers";
import { fakeServer } from "./test/fakeServer";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const FIXTURES = {
  pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE, ANSWER_PIPELINE],
  revisions: [TEMPLATE_REVISION, ANSWER_REVISION],
};

const pipelineNav = () => screen.getByRole("navigation", { name: "Pipelines of this profile" });
const link = (name: string) => within(pipelineNav()).getByRole("link", { name });

describe("the profile header on the canvas page", () => {
  it("opens a profile pipeline at its latest revision, with validate and run offered", async () => {
    const { user } = openStudio("#/studio/search-copy/search", FIXTURES);
    expect(await screen.findByRole("heading", { level: 1, name: "Search copy" })).toBeInTheDocument();
    await openAllSections(user);
    await within(outline()).findByRole("button", { name: /^Node rerank/ });
    expect(runPanel()).toHaveTextContent("The draft matches revision 1.");
    expect(within(runPanel()).getByRole("button", { name: "Validate" })).toBeEnabled();
    expect(within(runPanel()).getByRole("button", { name: "Run" })).toBeEnabled();
  });

  it("shows the title, the grey ID, the kind badge and the three purpose links", async () => {
    openStudio("#/studio/search-copy/search", FIXTURES);
    const heading = await screen.findByRole("heading", { level: 1, name: "Search copy" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const header = heading.closest("header") as HTMLElement;
    expect(within(header).getByText("Profile ID: search-copy")).toBeInTheDocument();
    expect(within(header).getByText("Your profile")).toBeInTheDocument();
    expect(within(header).queryByText("Not ready")).not.toBeInTheDocument();
    expect(within(pipelineNav()).getAllByRole("link").map((a) => a.textContent)).toEqual(["Ingest", "Search", "Answer"]);
    expect(link("Ingest")).toHaveAttribute("href", "#/studio/search-copy/ingest");
    expect(link("Search")).toHaveAttribute("href", "#/studio/search-copy/search");
    expect(link("Answer")).toHaveAttribute("href", "#/studio/search-copy/answer");
  });

  it("marks only the open purpose as current", async () => {
    openStudio("#/studio/search-copy/answer", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    expect(link("Answer")).toHaveAttribute("aria-current", "page");
    expect(link("Ingest")).not.toHaveAttribute("aria-current");
    expect(link("Search")).not.toHaveAttribute("aria-current");
  });

  it("opens Ingest when the route names no purpose", async () => {
    openStudio("#/studio/search-copy", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    expect(link("Ingest")).toHaveAttribute("aria-current", "page");
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(/graph is empty/);
    expect(window.location.hash).toBe("#/studio/search-copy");
  });

  it.each([
    ["ingest", "Reads files, splits them into chunks and stores them in the collection."],
    ["search", "Finds the chunks that best match a question."],
    ["answer", "Writes an answer from the best chunks and cites them."],
  ] as const)("describes the %s pipeline in one line", async (purpose, line) => {
    expect(PURPOSE_LINES[purpose]).toBe(line);
    const { user } = openStudio(`#/studio/search-copy/${purpose}`, FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    await screen.findByRole("button", { name: "Operations" });
    await user.click(screen.getByRole("button", { name: `About the ${PURPOSE_LABELS[purpose]} pipeline` }));
    expect(screen.getByText(line)).toBeInTheDocument();
    expect(screen.getAllByText(/^(Reads files|Finds the chunks|Writes an answer)/)).toHaveLength(1);
  });

  it("opens the slot pipeline of the link the user selects and adds a history entry", async () => {
    const { user } = openStudio("#/studio/search-copy/ingest", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Search copy" });
    await user.click(link("Search"));
    expect(window.location.hash).toBe("#/studio/search-copy/search");
    expect(link("Search")).toHaveAttribute("aria-current", "page");
    await openAllSections(user);
    expect(await within(outline()).findByRole("button", { name: /^Node rerank/ })).toBeInTheDocument();
  });

  it("shows an unsaved draft again after the user visits another purpose and comes back", async () => {
    const { user } = openStudio("#/studio/search-copy/ingest", FIXTURES);
    await screen.findByRole("region", { name: "Operations" });
    await addWithKeyboard(user, "Sparse retrieval", "retrieve.sparse");

    await user.click(link("Search"));
    await waitFor(() => expect(link("Search")).toHaveAttribute("aria-current", "page"));
    await openAllSections(user);
    expect(await within(outline()).findByRole("button", { name: /^Node rerank/ })).toBeInTheDocument();
    expect(within(outline()).queryByRole("button", { name: /^Node sparse / })).not.toBeInTheDocument();

    await user.click(link("Ingest"));
    await openAllSections(user);
    expect(await within(outline()).findByRole("button", { name: /^Node sparse/ })).toBeInTheDocument();
  });

  it("links back to the gallery with All profiles", async () => {
    const { user } = openStudio("#/studio/search-copy/search", FIXTURES);
    const back = await screen.findByRole("link", { name: "All profiles" });
    expect(back).toHaveAttribute("href", "#/studio");
    await user.click(back);
    expect(window.location.hash).toBe("#/studio");
    expect(await screen.findByRole("heading", { level: 1, name: "Studio" })).toBeInTheDocument();
  });

  it("shows the Not ready badge with the reasons", async () => {
    const notReady = { ...NOT_READY_PROFILE, slots: USER_PROFILE.slots };
    openStudio("#/studio/half-built/search", { ...FIXTURES, profiles: [notReady] });
    const heading = await screen.findByRole("heading", { level: 1, name: "Half built" });
    const header = heading.closest("header") as HTMLElement;
    expect(within(header).getByText("Not ready")).toBeInTheDocument();
    expect(within(header).getByText(NOT_READY_PROFILE.not_ready_reasons[0]!)).toBeInTheDocument();
  });

  it("shows the Built-in badge, the notice and Duplicate to edit for a built-in profile", async () => {
    openStudio("#/studio/documents/search", FIXTURES);
    const heading = await screen.findByRole("heading", { level: 1, name: "Documents" });
    const header = heading.closest("header") as HTMLElement;
    expect(within(header).getByText("Built-in")).toBeInTheDocument();
    expect(within(header).getByText("documents")).toBeInTheDocument();
    expect(screen.queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate to edit" })).toBeEnabled();
    expect(link("Search")).toHaveAttribute("aria-current", "page");
  });

  it("gives each pipeline tab an info button that opens that pipeline's description", async () => {
    const { user } = openStudio("#/studio/documents/search", FIXTURES);
    for (const [label, purpose] of [["Ingest", "ingest"], ["Search", "search"], ["Answer", "answer"]] as const) {
      const button = await screen.findByRole("button", { name: `About the ${label} pipeline` });
      expect(button).toHaveAttribute("aria-expanded", "false");
      expect(screen.queryByText(PURPOSE_LINES[purpose])).not.toBeInTheDocument();
      await user.click(button);
      expect(screen.getByText(PURPOSE_LINES[purpose])).toBeInTheDocument();
      await user.keyboard("{Escape}");
    }
  });

  it("shows no description line and no accordion in the header", async () => {
    openStudio("#/studio/documents/search", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Documents" });
    expect(screen.queryByText(PURPOSE_LINES.search)).not.toBeInTheDocument();
    expect(screen.queryByText("About this pipeline")).not.toBeInTheDocument();
    expect(document.querySelector("header details")).toBeNull();
  });

  it("shows the intro line once, above the pipeline tabs, without a click", async () => {
    openStudio("#/studio/documents/search", FIXTURES);
    const intro = await screen.findByText(CANVAS_INTRO);
    const tabs = screen.getByRole("navigation", { name: "Pipelines of this profile" });
    expect(intro.compareDocumentPosition(tabs) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(intro).toHaveClass("py-1");
    expect(screen.getAllByText(CANVAS_INTRO)).toHaveLength(1);
  });

  it("adds the read-only note to a built-in profile's popover, and not the intro line", async () => {
    const { user } = openStudio("#/studio/documents/search", FIXTURES);
    await user.click(await screen.findByRole("button", { name: "About the Search pipeline" }));
    const panel = screen.getByText(PURPOSE_LINES.search).closest("[data-slot='info-popover-content']") as HTMLElement;
    expect(within(panel).getByText(READ_ONLY_NOTICE)).toBeInTheDocument();
    expect(within(panel).queryByText(CANVAS_INTRO)).not.toBeInTheDocument();
    expect(screen.getAllByText(CANVAS_INTRO)).toHaveLength(1);
  });

  it("holds only the description in the popover of a profile that the user can edit", async () => {
    const { user } = openStudio("#/studio/search-copy/search", FIXTURES);
    await screen.findByRole("button", { name: "Operations" });
    await user.click(screen.getByRole("button", { name: "About the Search pipeline" }));
    const panel = screen.getByText(PURPOSE_LINES.search).closest("[data-slot='info-popover-content']") as HTMLElement;
    expect(within(panel).queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
    expect(within(panel).queryByText(CANVAS_INTRO)).not.toBeInTheDocument();
    expect(screen.getAllByText(CANVAS_INTRO)).toHaveLength(1);
  });

  it("shows the header toggle only when it is given a handler, and names it after the state", async () => {
    const onToggle = vi.fn();
    const render = (props: { collapsed?: boolean; onToggle?: () => void }) => (
      <ProfileHeader profile={USER_PROFILE} purpose="search" onDuplicate={vi.fn()} {...props} />
    );
    const options = { fetchImpl: fakeServer({ pipelines: FIXTURES.pipelines, revisions: FIXTURES.revisions }).fetchImpl };
    const { rerender } = renderWithProviders(render({ onToggle }), options);
    await userEvent.setup().click(screen.getByRole("button", { name: "Hide header" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    rerender(render({ onToggle, collapsed: true }));
    expect(screen.getByRole("button", { name: "Show header" })).toHaveAttribute("aria-expanded", "false");
    rerender(render({}));
    expect(screen.queryByRole("button", { name: /header$/ })).not.toBeInTheDocument();
  });

  it("puts Duplicate to edit to the left of All profiles", async () => {
    openStudio("#/studio/documents/search", FIXTURES);
    const duplicate = await screen.findByRole("button", { name: "Duplicate to edit" });
    const back = screen.getByRole("link", { name: "All profiles" });
    expect(duplicate.parentElement).toBe(back.parentElement);
    expect(duplicate.compareDocumentPosition(back) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it.each(["#/studio/missing", "#/studio/pl_1", "#/studio/missing/search"])("shows not found with a way back for %s", async (hash) => {
    openStudio(hash, FIXTURES);
    const name = hash.split("/")[2]!;
    expect(await screen.findByText(`The profile "${name}" could not be found.`)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Studio" })).toHaveAttribute("href", "#/studio");
    expect(window.location.hash).toBe(hash);
    expect(screen.queryByRole("navigation", { name: "Pipelines of this profile" })).not.toBeInTheDocument();
  });

  it("shows one friendly line with Retry when the profile cannot load", async () => {
    const { server, user } = openStudio("#/studio/search-copy/search", { ...FIXTURES, failures: { "GET /v1/profiles/search-copy": 500 } });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    delete server.failures["GET /v1/profiles/search-copy"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Search copy" })).toBeInTheDocument();
  });
});

describe("renaming from the canvas header", () => {
  it("updates the heading and the gallery card from one PATCH", async () => {
    const { server, user } = openStudio("#/studio/search-copy/search", FIXTURES);
    // The header is rebuilt when the pipeline finishes loading, so wait for the canvas first.
    await screen.findByRole("region", { name: "Operations" });
    await user.click(await screen.findByRole("button", { name: "Rename Search copy" }));
    const field = screen.getByRole("textbox", { name: "Profile title" });
    await user.clear(field);
    await user.type(field, "  Papers search  {Enter}");

    expect(await screen.findByRole("heading", { level: 1, name: "Papers search" })).toBeInTheDocument();
    expect(server.last("PATCH", "/v1/profiles/search-copy")?.body).toEqual({ title: "Papers search" });
    expect(screen.getByRole("button", { name: "Rename Papers search" })).toHaveFocus();

    await user.click(screen.getByRole("link", { name: "All profiles" }));
    expect(await screen.findByRole("group", { name: "Papers search" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Search copy" })).not.toBeInTheDocument();
  });

  it("offers no pencil on a built-in profile", async () => {
    openStudio("#/studio/documents/search", FIXTURES);
    await screen.findByRole("heading", { level: 1, name: "Documents" });
    expect(screen.queryByRole("button", { name: /^Rename/ })).not.toBeInTheDocument();
  });
});

describe("Duplicate to edit", () => {
  it("opens the dialog with a proposed title, creates the copy and opens it on Ingest, editable", async () => {
    const { server, user } = openStudio("#/studio/documents/search", FIXTURES);
    await user.click(await screen.findByRole("button", { name: "Duplicate to edit" }));
    const dialog = await screen.findByRole("dialog", { name: "Duplicate Documents" });
    expect(within(dialog).getByRole("textbox", { name: "Title" })).toHaveValue("Documents copy");
    await user.click(within(dialog).getByRole("button", { name: "Create profile" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/documents-copy"));
    expect(server.last("POST", "/v1/profiles")?.body).toEqual({ source: "documents", title: "Documents copy" });
    expect(await screen.findByRole("heading", { level: 1, name: "Documents copy" })).toBeInTheDocument();
    expect(link("Ingest")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rename Documents copy" })).toBeInTheDocument();
  });

  it("sends nothing when the user cancels", async () => {
    const { server, user } = openStudio("#/studio/documents/search", FIXTURES);
    await user.click(await screen.findByRole("button", { name: "Duplicate to edit" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(server.last("POST", "/v1/profiles")).toBeUndefined();
    expect(window.location.hash).toBe("#/studio/documents/search");
  });
});

describe("ProfileHeader", () => {
  const user = userEvent.setup();

  it("calls onDuplicate from Duplicate to edit and offers it for a built-in only", async () => {
    const onDuplicate = vi.fn();
    const { rerender } = renderWithProviders(<ProfileHeader profile={DOCUMENTS_PROFILE} purpose="search" onDuplicate={onDuplicate} />, {
      fetchImpl: fakeServer().fetchImpl,
    });
    await user.click(screen.getByRole("button", { name: "Duplicate to edit" }));
    expect(onDuplicate).toHaveBeenCalledTimes(1);

    rerender(<ProfileHeader profile={USER_PROFILE} purpose="search" onDuplicate={onDuplicate} />);
    expect(screen.queryByRole("button", { name: "Duplicate to edit" })).not.toBeInTheDocument();
    expect(screen.queryByText(READ_ONLY_NOTICE)).not.toBeInTheDocument();
  });
});
