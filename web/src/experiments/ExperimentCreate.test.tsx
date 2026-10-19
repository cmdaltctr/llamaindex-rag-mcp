import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { json } from "../test/fakeDocumentsServer";
import { entry } from "./test/experimentsServer";
import { openExperiments } from "./test/openExperiments";

async function chooseFolder(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(await screen.findByRole("combobox", { name: "Folder" }));
  await user.click(await screen.findByRole("option", { name }));
}

describe("creating a folder", () => {
  it("creates a main folder below the approved root and lists it", async () => {
    const { server, user } = openExperiments();
    const form = await screen.findByRole("form", { name: "Create a folder" });
    await user.type(within(form).getByLabelText("Folder name"), "hybrid-search");
    await user.click(within(form).getByRole("button", { name: "Create folder" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiment-folders")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiment-folders")[0]!.body).toEqual({ path: "hybrid-search", root: null });
    const created = await screen.findByRole("group", { name: "Folder hybrid-search" });
    expect(within(created).getByText(/Empty folder/)).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Created folder hybrid-search.");
  });

  it("names the root and sends it when the server approves more than one", async () => {
    const { server, user } = openExperiments({ roots: ["/srv/exp", "/srv/other"] });
    const form = await screen.findByRole("form", { name: "Create a folder" });
    await user.click(within(form).getByRole("combobox", { name: "Experiment root" }));
    await user.click(await screen.findByRole("option", { name: "/srv/other" }));
    await user.type(within(form).getByLabelText("Folder name"), "x");
    await user.click(within(form).getByRole("button", { name: "Create folder" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiment-folders")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiment-folders")[0]!.body).toEqual({ path: "x", root: "/srv/other" });
  });

  it("shows a friendly line beside the field for a refused path and creates nothing", async () => {
    const { server, user } = openExperiments();
    const form = await screen.findByRole("form", { name: "Create a folder" });
    const field = within(form).getByLabelText("Folder name");
    await user.type(field, "../escape");
    await user.click(within(form).getByRole("button", { name: "Create folder" }));
    const message = await within(form).findByRole("alert");
    expect(message).toHaveTextContent('A folder name cannot contain "..".');
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(expect.stringContaining("cannot contain"));
    expect(document.body.textContent).not.toContain("RAW");
    expect(screen.queryByRole("group", { name: /Folder/ })).toBeNull();
    expect(server.state.dirs).toEqual([]);
  });

  it("says the folder exists when the server answers 409 exists", async () => {
    const { user } = openExperiments({ dirs: ["hybrid-search"] });
    const form = await screen.findByRole("form", { name: "Create a folder" });
    await user.type(within(form).getByLabelText("Folder name"), "hybrid-search");
    await user.click(within(form).getByRole("button", { name: "Create folder" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("That folder already exists.");
  });

  it.each([
    ["not_relative", /inside the root/],
    ["too_deep", /four levels/],
    ["invalid_name", /letters, numbers/i],
    ["symlink_escape", /link/],
    ["not_a_directory", /file already/],
    ["root_unknown", /not approved/],
    ["root_required", /Choose a root/],
  ])("maps the refusal code %s to its own line", async (code, line) => {
    const { user } = openExperiments({}, { "POST /v1/experiment-folders": () => json({ status: "error", code, message: "RAW" }, 400) });
    const form = await screen.findByRole("form", { name: "Create a folder" });
    await user.type(within(form).getByLabelText("Folder name"), "x");
    await user.click(within(form).getByRole("button", { name: "Create folder" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(line);
    expect(document.body.textContent).not.toContain("RAW");
  });
});

describe("creating a sub-experiment", () => {
  it("creates its folder, then registers a context with the declared factors", async () => {
    const { server, user } = openExperiments({ dirs: ["hybrid-search"] });
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    await chooseFolder(user, "hybrid-search");
    await user.type(within(form).getByLabelText("Name"), "run-1");
    await user.type(within(form).getByLabelText("Declared factors"), "chunk-size, reranker");
    await user.click(within(form).getByRole("button", { name: "Create sub-experiment" }));

    await waitFor(() => expect(server.find("POST", "/v1/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiment-folders")[0]!.body).toEqual({ path: "hybrid-search/run-1", root: null });
    expect(server.find("POST", "/v1/experiments")[0]!.body).toEqual({
      workspace: "/srv/exp/hybrid-search/run-1",
      name: "run-1",
      actions: ["read", "ingest"],
      declared_factors: ["chunk-size", "reranker"],
    });
    const folder = await screen.findByRole("group", { name: "Folder hybrid-search" });
    const row = await within(folder).findByRole("group", { name: "Experiment run-1" });
    expect(within(row).getByText("chunk-size")).toBeInTheDocument();
    expect(within(row).getByText("reranker")).toBeInTheDocument();
  });

  it("sends only the permitted actions that are ticked", async () => {
    const { server, user } = openExperiments({ dirs: ["f"] });
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    await chooseFolder(user, "f");
    await user.type(within(form).getByLabelText("Name"), "a");
    await user.click(within(form).getByRole("checkbox", { name: "Ingest into the experiment store" }));
    await user.click(within(form).getByRole("button", { name: "Create sub-experiment" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiments")[0]!.body).toMatchObject({ actions: ["read"], declared_factors: [] });
  });

  it("registers in the folder that already exists after an earlier half-finished attempt", async () => {
    const { server, user } = openExperiments({ dirs: ["f", "f/run-1"] });
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    await chooseFolder(user, "f");
    await user.type(within(form).getByLabelText("Name"), "run-1");
    await user.click(within(form).getByRole("button", { name: "Create sub-experiment" }));
    await waitFor(() => expect(server.find("POST", "/v1/experiments")).toHaveLength(1));
    expect(server.find("POST", "/v1/experiments")[0]!.body).toMatchObject({ workspace: "/srv/exp/f/run-1" });
  });

  it("asks for a folder first when none exists, and disables the button", async () => {
    const { server } = openExperiments();
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    expect(within(form).getByText(/Create a folder first/)).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Create sub-experiment" })).toBeDisabled();
    expect(server.find("POST", "/v1/experiments")).toHaveLength(0);
  });

  it("refuses more than eight factors before any request", async () => {
    const { server, user } = openExperiments({ dirs: ["f"] });
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    await chooseFolder(user, "f");
    await user.type(within(form).getByLabelText("Name"), "a");
    await user.type(within(form).getByLabelText("Declared factors"), "a,b,c,d,e,f,g,h,i");
    await user.click(within(form).getByRole("button", { name: "Create sub-experiment" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/at most eight/i);
    expect(server.find("POST", "/v1/experiment-folders")).toHaveLength(0);
    expect(server.find("POST", "/v1/experiments")).toHaveLength(0);
  });

  it("keeps a context listed after a refusal of the registration", async () => {
    const { user } = openExperiments(
      { dirs: ["f"], entries: [entry("exp_1", "a", "active", "f/a")] },
      { "POST /v1/experiments": () => json({ status: "error", code: "overlaps_context", message: "RAW overlap" }, 400) },
    );
    const form = await screen.findByRole("form", { name: "Create a sub-experiment" });
    await chooseFolder(user, "f");
    await user.type(within(form).getByLabelText("Name"), "b");
    await user.click(within(form).getByRole("button", { name: "Create sub-experiment" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/overlaps/i);
    expect(document.body.textContent).not.toContain("RAW");
    expect(screen.getByRole("group", { name: "Experiment a" })).toBeInTheDocument();
  });
});
