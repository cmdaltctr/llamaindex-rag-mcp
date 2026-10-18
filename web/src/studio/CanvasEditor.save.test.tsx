import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { saveWarning } from "./profileCopy";
import { addWithKeyboard, ANSWER_PIPELINE, ANSWER_REVISION, EMPTY_PIPELINE, findPalette, openAllSections, runPanel, TEMPLATE_PIPELINE, TEMPLATE_REVISION, USER_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const PIPELINES = [EMPTY_PIPELINE, TEMPLATE_PIPELINE, ANSWER_PIPELINE];
const REVISIONS = [TEMPLATE_REVISION, ANSWER_REVISION];

async function setup(purpose: "ingest" | "search" | "answer", usedBy: string[]) {
  const profile = { ...USER_PROFILE, used_by: usedBy };
  const view = openStudio(`#/studio/search-copy/${purpose}`, { pipelines: PIPELINES, revisions: REVISIONS, profiles: [profile] });
  await findPalette();
  await addWithKeyboard(view.user, "Sparse retrieval", "retrieve.sparse");
  await openAllSections(view.user);
  return view;
}

const saveButton = () => within(runPanel()).getByRole("button", { name: "Save revision" });
const posts = (server: Awaited<ReturnType<typeof setup>>["server"]) => server.calls.filter((call) => call.method === "POST" && call.path.endsWith("/revisions"));

describe("saving a pipeline of a profile in use", () => {
  it("asks first for the Search pipeline and names both collections", async () => {
    const { server, user } = await setup("search", ["papers", "notes"]);
    await user.click(saveButton());
    const dialog = await screen.findByRole("dialog", { name: "Save this revision?" });
    expect(within(dialog).getByText("Saving changes how 2 collections are searched: papers, notes.")).toBeInTheDocument();
    expect(saveWarning("search", ["papers", "notes"])).toBe("Saving changes how 2 collections are searched: papers, notes.");
    expect(posts(server)).toHaveLength(0);
  });

  it("says how one collection answers questions for the Answer pipeline", async () => {
    const { user } = await setup("answer", ["papers"]);
    await user.click(saveButton());
    expect(await screen.findByText("Saving changes how 1 collection answers questions: papers.")).toBeInTheDocument();
  });

  it("adds the old-chunks line for the Ingest pipeline", async () => {
    const { user } = await setup("ingest", ["papers"]);
    await user.click(saveButton());
    expect(
      await screen.findByText("Saving changes how 1 collection ingests files: papers. Documents already in these collections keep their old chunks until you ingest them again."),
    ).toBeInTheDocument();
  });

  it("saves only after the user confirms, and names the affected collections in the status line", async () => {
    const { server, user } = await setup("search", ["papers", "notes"]);
    await user.click(saveButton());
    const dialog = await screen.findByRole("dialog", { name: "Save this revision?" });
    expect(posts(server)).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Save revision" }));
    await waitFor(() => expect(posts(server)).toHaveLength(1));
    expect(await screen.findByText("Saved revision 2. It now applies to 2 collections: papers, notes.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sends nothing and keeps the draft when the user cancels", async () => {
    const { server, user } = await setup("search", ["papers"]);
    await user.click(saveButton());
    const dialog = await screen.findByRole("dialog", { name: "Save this revision?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posts(server)).toHaveLength(0);
    expect(within(runPanel()).getByText(/The draft differs from revision 1/)).toBeInTheDocument();
    expect(saveButton()).toHaveFocus();
  });

  it("saves with no dialog when no collection uses the profile", async () => {
    const { server, user } = await setup("search", []);
    await user.click(saveButton());
    await waitFor(() => expect(posts(server)).toHaveLength(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText("Saved revision 2.")).toBeInTheDocument();
  });
});
