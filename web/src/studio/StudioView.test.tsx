import { screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { PROFILE_HELP_LINES, STUDIO_SUMMARY } from "./profileCopy";
import { CODEBASE_PROFILE, DOCUMENTS_PROFILE, NOT_READY_PROFILE, USER_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const card = (name: string) => screen.getByRole("group", { name });
const section = (name: string) => screen.getByRole("region", { name });
const PAPERS = { ...USER_PROFILE, profile_id: "papers-search", title: "Papers search", used_by: ["papers", "notes"] };

describe("Studio header", () => {
  it("explains what a profile is in two sentences and drops the old summary", () => {
    openStudio("#/studio");
    expect(screen.getByRole("heading", { level: 1, name: "Studio" })).toBeInTheDocument();
    expect(STUDIO_SUMMARY).toBe(
      "Profiles are groups of steps that you connect into pipelines to ingest files, search them and answer questions. Each collection uses one profile, and the profile decides how that collection works.",
    );
    expect(screen.getByText(STUDIO_SUMMARY)).toBeInTheDocument();
    expect(screen.queryByText("Build pipelines from templates and run them.")).toBeNull();
  });

  it("keeps the four lines in a disclosure that starts closed", async () => {
    const { user } = openStudio("#/studio");
    const summary = screen.getByText("How profiles work");
    const details = summary.closest("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    expect(PROFILE_HELP_LINES).toHaveLength(4);
    expect(PROFILE_HELP_LINES[0]).toBe("Built-in profiles come with OMRG and are read-only. Your profiles are copies that you can rename, change and delete.");
    expect(PROFILE_HELP_LINES[3]).toBe("When a collection holds vectors, the embedding model of its profile is locked, because the stored vectors were made with that model.");
    expect(within(details!).getAllByRole("listitem", { hidden: true }).map((line) => line.textContent)).toEqual(PROFILE_HELP_LINES);
    await user.click(summary);
    expect(details).toHaveAttribute("open");
  });
});

describe("Studio gallery", () => {
  it("lists built-in profiles and your profiles in two sections, ending with the empty-profile card", async () => {
    openStudio("#/studio");
    const builtIn = within(await screen.findByRole("region", { name: "Built-in profiles" }));
    expect(await builtIn.findByRole("group", { name: "Documents" })).toBeInTheDocument();
    expect(builtIn.getByRole("group", { name: "Codebase" })).toBeInTheDocument();
    const yours = within(section("Your profiles"));
    const cards = yours.getAllByRole("group");
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveAccessibleName("Search copy");
    expect(cards[1]).toHaveAccessibleName("Half built");
    expect(cards[2]).toHaveAccessibleName("New empty profile");
  });

  it("drops the template, preset and saved pipeline sections and never asks for them", async () => {
    const { server } = openStudio("#/studio");
    await screen.findByRole("group", { name: "Documents" });
    for (const name of ["Templates", "Profile presets", "Saved pipelines"]) {
      expect(screen.queryByRole("region", { name })).toBeNull();
      expect(screen.queryByRole("heading", { name })).toBeNull();
    }
    expect(screen.queryByText("Create pipeline")).toBeNull();
    expect(server.calls.filter((call) => call.path === "/v1/pipeline-templates" || call.path === "/v1/pipelines")).toEqual([]);
  });

  it("shows the title, the grey ID and how many collections use the profile", async () => {
    openStudio("#/studio", { profiles: [DOCUMENTS_PROFILE, CODEBASE_PROFILE, PAPERS] });
    const papers = within(await screen.findByRole("group", { name: "Papers search" }));
    expect(papers.getByRole("heading", { level: 3, name: "Papers search" })).toBeInTheDocument();
    expect(papers.getByText("Profile ID: papers-search")).toBeInTheDocument();
    expect(papers.getByText("Used by 2 collections")).toBeInTheDocument();
    expect(within(card("Documents")).getByText("Used by 1 collection")).toBeInTheDocument();
    expect(within(card("Documents")).getByText("Profile ID: documents")).toBeInTheDocument();
    expect(within(card("Documents")).getByText(DOCUMENTS_PROFILE.description)).toBeInTheDocument();
  });

  it("says when no collection uses a profile", async () => {
    openStudio("#/studio");
    expect(within(await screen.findByRole("group", { name: "Codebase" })).getByText("Not used by any collection")).toBeInTheDocument();
  });

  it("offers Open profile and Duplicate on a built-in card, without a pencil or Delete", async () => {
    openStudio("#/studio");
    const documents = within(await screen.findByRole("group", { name: "Documents" }));
    expect(documents.getByRole("link", { name: "Open profile" })).toHaveAttribute("href", "#/studio/documents");
    expect(documents.getByRole("button", { name: "Duplicate" })).toBeEnabled();
    expect(documents.queryByRole("button", { name: /^Rename/ })).toBeNull();
    expect(documents.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("offers a pencil and Delete on a user profile card as well", async () => {
    openStudio("#/studio");
    const copy = within(await screen.findByRole("group", { name: "Search copy" }));
    expect(copy.getByRole("link", { name: "Open profile" })).toHaveAttribute("href", "#/studio/search-copy");
    expect(copy.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();
    expect(copy.getByRole("button", { name: "Rename Search copy" })).toBeInTheDocument();
    expect(copy.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("marks a profile that is not ready and prints each reason as text", async () => {
    openStudio("#/studio", { profiles: [DOCUMENTS_PROFILE, { ...NOT_READY_PROFILE, not_ready_reasons: ["The Answer pipeline has no `answer` output.", "The Search pipeline has no saved revision."] }] });
    const half = within(await screen.findByRole("group", { name: "Half built" }));
    expect(half.getByText("Not ready")).toBeInTheDocument();
    expect(half.getByText("The Answer pipeline has no `answer` output.")).toBeInTheDocument();
    expect(half.getByText("The Search pipeline has no saved revision.")).toBeInTheDocument();
    expect(within(card("Documents")).queryByText("Not ready")).toBeNull();
  });

  it("opens a profile on its Ingest pipeline through the Open profile link", async () => {
    const { user } = openStudio("#/studio", { profiles: [DOCUMENTS_PROFILE, PAPERS] });
    const link = within(await screen.findByRole("group", { name: "Papers search" })).getByRole("link", { name: "Open profile" });
    expect(link).toHaveAttribute("href", "#/studio/papers-search");
    await user.click(link);
    expect(window.location.hash).toBe("#/studio/papers-search");
  });

  it("states that there are no user profiles yet and keeps the empty-profile card", async () => {
    openStudio("#/studio", { profiles: [DOCUMENTS_PROFILE, CODEBASE_PROFILE] });
    const yours = within(section("Your profiles"));
    expect(await yours.findByText("You have no profiles yet. Duplicate a built-in profile or start an empty one.")).toBeInTheDocument();
    expect(yours.getByRole("group", { name: "New empty profile" })).toBeInTheDocument();
  });

  it("shows one friendly line with Retry when the listing fails, and keeps the empty-profile card enabled", async () => {
    const { server, user } = openStudio("#/studio", { failures: { "GET /v1/profiles": 500 } });
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(within(card("New empty profile")).getByRole("button", { name: "New empty profile" })).toBeEnabled();

    delete server.failures["GET /v1/profiles"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("group", { name: "Documents" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
