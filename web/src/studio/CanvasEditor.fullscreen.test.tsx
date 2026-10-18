import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { EMPTY_PIPELINE, openAllSections, outline, TEMPLATE_PIPELINE, TEMPLATE_REVISION, USER_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const FIXTURES = { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], profiles: [USER_PROFILE] };

async function openUser() {
  const view = openStudio("#/studio/search-copy/search", FIXTURES);
  await screen.findByRole("toolbar", { name: "View controls" });
  await waitFor(() => expect(document.querySelectorAll(".react-flow__node")).toHaveLength(4));
  return view;
}

const enterButton = () => within(screen.getByRole("toolbar", { name: "View controls" })).getByRole("button", { name: "Full screen" });
const exitButton = () => screen.queryByRole("button", { name: "Exit full screen" });
const nav = () => screen.queryByRole("navigation", { name: "Workspace" });

describe("canvas full screen", () => {
  it("shows the canvas, the toolbar, the panel and an X button, and moves focus to the X", async () => {
    const { user } = await openUser();
    expect(nav()).toBeInTheDocument();
    await user.click(enterButton());
    expect(await screen.findByRole("button", { name: "Exit full screen" })).toHaveFocus();
    expect(nav()).not.toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Pipeline settings" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("toolbar", { name: "View controls" })).toBeInTheDocument();
    expect(document.querySelectorAll(".react-flow__node")).toHaveLength(4);
  });

  it("leaves with the X button, keeps the selected step and returns focus to the full screen button", async () => {
    const { user } = await openUser();
    await openAllSections(user);
    await user.click(within(outline()).getByRole("button", { name: /^Node rerank/ }));
    await waitFor(() => expect(document.querySelector('.react-flow__node[data-id="rerank"]')).toHaveClass("selected"));
    await user.click(enterButton());
    await user.click(await screen.findByRole("button", { name: "Exit full screen" }));
    expect(exitButton()).not.toBeInTheDocument();
    expect(nav()).toBeInTheDocument();
    expect(document.querySelector('.react-flow__node[data-id="rerank"]')).toHaveClass("selected");
    expect(enterButton()).toHaveFocus();
  });

  it("leaves with Escape and returns focus to the full screen button", async () => {
    const { user } = await openUser();
    await user.click(enterButton());
    await screen.findByRole("button", { name: "Exit full screen" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(exitButton()).not.toBeInTheDocument());
    expect(nav()).toBeInTheDocument();
    expect(enterButton()).toHaveFocus();
  });

  it("ignores Escape while focus is in a text field", async () => {
    const { user } = await openUser();
    await user.click(enterButton());
    await screen.findByRole("button", { name: "Exit full screen" });
    const field = document.createElement("input");
    document.body.append(field);
    field.focus();
    fireEvent.keyDown(field, { key: "Escape" });
    expect(exitButton()).toBeInTheDocument();
    field.remove();
  });

  it("ends when the user leaves the canvas", async () => {
    const { user } = await openUser();
    await user.click(enterButton());
    await screen.findByRole("button", { name: "Exit full screen" });
    act(() => {
      window.location.hash = "#/studio";
    });
    expect(await screen.findByRole("navigation", { name: "Workspace" })).toBeInTheDocument();
    expect(exitButton()).not.toBeInTheDocument();
  });
});
