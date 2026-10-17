import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { USER_PROFILE, NOT_READY_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const UNUSED = { ...USER_PROFILE, used_by: [] };
const deletes = (server: ReturnType<typeof openStudio>["server"]) => server.calls.filter((call) => call.method === "DELETE");

describe("DeleteProfileDialog", () => {
  it("asks first, deletes once, removes the card and says Profile deleted.", async () => {
    const { server, user } = openStudio("#/studio", { profiles: [UNUSED, NOT_READY_PROFILE] });
    const card = within(await screen.findByRole("group", { name: "Search copy" }));
    await user.click(card.getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog", { name: "Delete Search copy?" });
    expect(within(dialog).getByText("Collections can no longer pick this profile. Past runs stay in Experiments.")).toBeInTheDocument();
    expect(deletes(server)).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Delete profile" }));

    await waitFor(() => expect(screen.queryByRole("group", { name: "Search copy" })).toBeNull());
    expect(deletes(server)).toHaveLength(1);
    expect(deletes(server)[0]?.path).toBe("/v1/profiles/search-copy");
    expect(await screen.findByRole("status")).toHaveTextContent("Profile deleted.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("group", { name: "Half built" })).toBeInTheDocument();
  });

  it("disables Delete while collections use the profile and says why in visible text", async () => {
    const used = { ...USER_PROFILE, used_by: ["papers", "notes"] };
    const { server } = openStudio("#/studio", { profiles: [used] });
    const card = within(await screen.findByRole("group", { name: "Search copy" }));
    expect(card.getByRole("button", { name: "Delete" })).toBeDisabled();
    expect(
      card.getByText("You cannot delete this profile while collections use it: papers, notes. Pick another profile for them in Knowledge Base first."),
    ).toBeVisible();
    expect(deletes(server)).toHaveLength(0);
  });

  it("does not show the reason when the profile is free to delete", async () => {
    openStudio("#/studio", { profiles: [UNUSED] });
    const card = within(await screen.findByRole("group", { name: "Search copy" }));
    expect(card.getByRole("button", { name: "Delete" })).toBeEnabled();
    expect(card.queryByText(/You cannot delete this profile/)).toBeNull();
  });

  it("names the collections from a 409 refusal and keeps the card", async () => {
    const { server, user } = openStudio("#/studio", { profiles: [UNUSED] });
    const card = within(await screen.findByRole("group", { name: "Search copy" }));
    // The collection picked the profile after the list loaded.
    server.profiles.get("search-copy")!.used_by = ["papers"];
    await user.click(card.getByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete profile" }));

    const dialog = await screen.findByRole("dialog", { name: "Delete Search copy?" });
    expect(await within(dialog).findByText("You cannot delete this profile while collections use it: papers.")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Search copy", hidden: true })).toBeInTheDocument();
    expect(screen.queryByText("Profile deleted.")).toBeNull();
    expect(deletes(server)).toHaveLength(1);
  });

  it("shows a friendly line with Retry for another failure and keeps the card", async () => {
    const { user } = openStudio("#/studio", { profiles: [UNUSED], failures: { "DELETE /v1/profiles/search-copy": 500 } });
    const card = within(await screen.findByRole("group", { name: "Search copy" }));
    await user.click(card.getByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete profile" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(screen.getByRole("group", { name: "Search copy", hidden: true })).toBeInTheDocument();
  });

  it("sends nothing on Cancel and returns focus to the Delete button", async () => {
    const { server, user } = openStudio("#/studio", { profiles: [UNUSED] });
    const button = within(await screen.findByRole("group", { name: "Search copy" })).getByRole("button", { name: "Delete" });
    await user.click(button);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(deletes(server)).toHaveLength(0);
    expect(button).toHaveFocus();
  });

  it("sends nothing on Escape and returns focus to the Delete button", async () => {
    const { server, user } = openStudio("#/studio", { profiles: [UNUSED] });
    const button = within(await screen.findByRole("group", { name: "Search copy" })).getByRole("button", { name: "Delete" });
    await user.click(button);
    await user.keyboard("{Escape}");
    expect(deletes(server)).toHaveLength(0);
    expect(button).toHaveFocus();
  });
});
