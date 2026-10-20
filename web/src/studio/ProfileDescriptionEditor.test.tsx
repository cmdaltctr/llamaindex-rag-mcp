import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../test/providers";
import { ProfileDescriptionEditor } from "./ProfileDescriptionEditor";
import { fakeServer } from "./test/fakeServer";
import { DOCUMENTS_PROFILE, USER_PROFILE } from "./test/helpers";

const PATH = "/v1/profiles/search-copy";
const DESCRIBED = { ...USER_PROFILE, description: "Old words" };

function setup(profile = DESCRIBED, failures: Record<string, number> = {}) {
  const server = fakeServer({ failures });
  renderWithProviders(<ProfileDescriptionEditor profile={profile} />, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

const pencil = () => screen.getByRole("button", { name: "Edit the description of Search copy" });
const field = () => screen.getByRole("textbox", { name: "Profile description" });
const patches = (server: ReturnType<typeof fakeServer>) => server.calls.filter((call) => call.method === "PATCH");

describe("ProfileDescriptionEditor", () => {
  it("shows the description and a pencil for a user profile", () => {
    setup();
    expect(screen.getByText("Old words")).toBeInTheDocument();
    expect(pencil()).toBeInTheDocument();
  });

  it("says when a user profile has no description", () => {
    setup(USER_PROFILE);
    expect(screen.getByText("No description")).toBeInTheDocument();
  });

  it("sends the trimmed description on Enter", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    expect(field()).toHaveValue("Old words");
    await user.clear(field());
    await user.type(field(), "  Papers for the fellowship review {Enter}");
    await waitFor(() => expect(patches(server)).toHaveLength(1));
    expect(patches(server)[0]).toMatchObject({ path: PATH, body: { description: "Papers for the fellowship review" } });
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  });

  it("cancels on Escape with no request and returns focus to the pencil", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.type(field(), " changed{Escape}");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(patches(server)).toHaveLength(0);
    expect(screen.getByText("Old words")).toBeInTheDocument();
    expect(pencil()).toHaveFocus();
  });

  it("refuses more than 1000 characters and sends nothing", async () => {
    const { server, user } = setup(USER_PROFILE);
    await user.click(pencil());
    await user.click(field());
    await user.paste("x".repeat(1001));
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Use at most 1000 characters.");
    expect(patches(server)).toHaveLength(0);
  });

  it("keeps the old description and offers Retry when the save fails", async () => {
    const { server, user } = setup(DESCRIBED, { [`PATCH ${PATH}`]: 500 });
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "New words{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).not.toHaveTextContent("Boom");
    expect(screen.getByText("Old words")).toBeInTheDocument();
    delete server.failures[`PATCH ${PATH}`];
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(patches(server)).toHaveLength(2));
    expect(patches(server)[1]?.body).toEqual({ description: "New words" });
  });

  it("shows a built-in description with no pencil", () => {
    setup({ ...DOCUMENTS_PROFILE, description: "General documents." });
    expect(screen.getByText("General documents.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
