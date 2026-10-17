import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { RouteProvider } from "../lib/RouteProvider";
import { renderWithProviders } from "../test/providers";
import { NewProfileDialog } from "./NewProfileDialog";
import { fakeServer } from "./test/fakeServer";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const posts = (server: ReturnType<typeof openStudio>["server"]) => server.calls.filter((call) => call.method === "POST" && call.path === "/v1/profiles");
const titleField = () => screen.getByRole("textbox", { name: "Title" });

async function openDuplicate(name = "Documents") {
  const context = openStudio("#/studio");
  const opener = within(await screen.findByRole("group", { name })).getByRole("button", { name: "Duplicate" });
  await context.user.click(opener);
  return { ...context, opener };
}

describe("NewProfileDialog", () => {
  it("duplicates a built-in profile with the proposed title and opens the new profile", async () => {
    const { server, user } = await openDuplicate();
    const dialog = screen.getByRole("dialog", { name: "Duplicate Documents" });
    expect(within(dialog).getByText("The profile ID is made from this title. It cannot change later.")).toBeInTheDocument();
    expect(titleField()).toHaveValue("Documents copy");
    expect(titleField()).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Create profile" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/documents-copy"));
    expect(posts(server)).toHaveLength(1);
    expect(posts(server)[0]?.body).toEqual({ source: "documents", title: "Documents copy" });
    expect(screen.queryByRole("dialog", { name: "Duplicate Documents" })).toBeNull();
  });

  it("proposes the source title plus copy for a user profile too", async () => {
    await openDuplicate("Search copy");
    expect(titleField()).toHaveValue("Search copy copy");
  });

  it("starts an empty profile with source null and the typed title", async () => {
    const { server, user } = openStudio("#/studio");
    await user.click(within(await screen.findByRole("group", { name: "New empty profile" })).getByRole("button", { name: "New empty profile" }));
    const dialog = screen.getByRole("dialog", { name: "New empty profile" });
    expect(titleField()).toHaveValue("");
    await user.type(titleField(), "Notes");
    await user.click(within(dialog).getByRole("button", { name: "Create profile" }));

    await waitFor(() => expect(window.location.hash).toBe("#/studio/notes"));
    expect(posts(server)[0]?.body).toEqual({ source: null, title: "Notes" });
  });

  it("refuses a title of spaces with Enter a title. and sends nothing", async () => {
    const { server, user } = await openDuplicate();
    await user.clear(titleField());
    await user.type(titleField(), "   ");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(await screen.findByText("Enter a title.")).toBeInTheDocument();
    expect(posts(server)).toHaveLength(0);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("stays open with the typed title and one friendly line when the server refuses", async () => {
    const { server, user } = openStudio("#/studio", { failures: { "POST /v1/profiles": 500 } });
    await user.click(within(await screen.findByRole("group", { name: "Documents" })).getByRole("button", { name: "Duplicate" }));
    await user.clear(titleField());
    await user.type(titleField(), "Mine");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The local server could not complete that request.");
    expect(alert).not.toHaveTextContent("Boom");
    expect(titleField()).toHaveValue("Mine");
    expect(window.location.hash).toBe("#/studio");

    delete server.failures["POST /v1/profiles"];
    await user.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(window.location.hash).toBe("#/studio/mine"));
  });

  it("sends nothing on Cancel and returns focus to the button that opened the dialog", async () => {
    const { server, user, opener } = await openDuplicate();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(posts(server)).toHaveLength(0);
    expect(opener).toHaveFocus();
  });

  it("sends nothing on Escape and returns focus to the button that opened the dialog", async () => {
    const { server, user, opener } = await openDuplicate();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(posts(server)).toHaveLength(0);
    expect(opener).toHaveFocus();
  });

  it("starts with a fresh proposal each time it opens", async () => {
    const { user } = await openDuplicate();
    await user.clear(titleField());
    await user.type(titleField(), "Draft");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(within(screen.getByRole("group", { name: "Documents" })).getByRole("button", { name: "Duplicate" }));
    expect(titleField()).toHaveValue("Documents copy");
  });

  it("asks its owner to close the dialog when the profile is created", async () => {
    const onOpenChange = vi.fn();
    window.history.replaceState(null, "", "/#/studio");
    renderWithProviders(
      <RouteProvider>
        <NewProfileDialog source={null} open onOpenChange={onOpenChange} />
      </RouteProvider>,
      { fetchImpl: fakeServer().fetchImpl },
    );
    const user = userEvent.setup();
    await user.type(titleField(), "Notes");
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    await waitFor(() => expect(window.location.hash).toBe("#/studio/notes"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
