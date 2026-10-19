import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeServer } from "./test/fakeServer";
import { DOCUMENTS_PROFILE, USER_PROFILE } from "./test/helpers";
import { renderWithProviders } from "../test/providers";
import { ProfileTitleEditor } from "./ProfileTitleEditor";

const PATH = "/v1/profiles/search-copy";

function setup(profile = USER_PROFILE, failures: Record<string, number> = {}, level?: 1 | 2 | 3) {
  const server = fakeServer({ failures });
  renderWithProviders(<ProfileTitleEditor profile={profile} level={level} />, { fetchImpl: server.fetchImpl });
  return { server, user: userEvent.setup() };
}

const pencil = () => screen.getByRole("button", { name: "Rename Search copy" });
const field = () => screen.getByRole("textbox", { name: "Profile title" });
const patches = (server: ReturnType<typeof fakeServer>) => server.calls.filter((call) => call.method === "PATCH");

describe("ProfileTitleEditor", () => {
  it("shows the title, a pencil and the grey profile ID of a user profile", () => {
    setup();
    expect(screen.getByRole("heading", { level: 2, name: "Search copy" })).toBeInTheDocument();
    expect(screen.getByText("Profile ID: search-copy")).toBeInTheDocument();
    expect(pencil()).toBeInTheDocument();
  });

  it("uses the heading level it is given", () => {
    setup(USER_PROFILE, {}, 1);
    expect(screen.getByRole("heading", { level: 1, name: "Search copy" })).toBeInTheDocument();
  });

  it("shows only the title for a built-in profile, with no pencil", () => {
    setup(DOCUMENTS_PROFILE);
    expect(screen.getByRole("heading", { level: 2, name: "Documents" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/Profile ID/)).toBeNull();
  });

  it("opens a field with the current title and focuses it", async () => {
    const { user } = setup();
    await user.click(pencil());
    expect(field()).toHaveValue("Search copy");
    expect(field()).toHaveFocus();
  });

  it("sends the trimmed title with PATCH on Enter", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "  Papers, strict  {Enter}");
    await waitFor(() => expect(patches(server)).toHaveLength(1));
    expect(patches(server)[0]).toMatchObject({ path: PATH, body: { title: "Papers, strict" } });
  });

  it("sends the title when Save is selected", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.type(field(), " two");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(patches(server)).toHaveLength(1));
    expect(patches(server)[0]?.body).toEqual({ title: "Search copy two" });
  });

  it("refuses an empty title with Enter a title. and sends nothing", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "   {Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a title.");
    expect(patches(server)).toHaveLength(0);
    expect(field()).toBeInTheDocument();
  });

  it("cancels on Escape with no request, keeps the title and returns focus to the pencil", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.type(field(), " changed{Escape}");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(patches(server)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Search copy" })).toBeInTheDocument();
    expect(pencil()).toHaveFocus();
  });

  it("cancels with the Cancel button and sends nothing", async () => {
    const { server, user } = setup();
    await user.click(pencil());
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(patches(server)).toHaveLength(0);
    expect(pencil()).toHaveFocus();
  });

  it("returns focus to the pencil after a save", async () => {
    const { user } = setup();
    await user.click(pencil());
    await user.type(field(), "x{Enter}");
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(pencil()).toHaveFocus();
  });

  it("keeps the old title and shows one friendly line with Retry when the server refuses", async () => {
    const { server, user } = setup(USER_PROFILE, { [`PATCH ${PATH}`]: 500 });
    await user.click(pencil());
    await user.clear(field());
    await user.type(field(), "Renamed{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(screen.getByRole("heading", { name: "Search copy" })).toBeInTheDocument();

    delete server.failures[`PATCH ${PATH}`];
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(patches(server)).toHaveLength(2));
    expect(patches(server)[1]?.body).toEqual({ title: "Renamed" });
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});
