import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { EMPTY_PIPELINE, openAllSections, runPanel, TEMPLATE_PIPELINE, TEMPLATE_REVISION, USER_PROFILE } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const FIXTURES = { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION], profiles: [USER_PROFILE] };
const STEPS = ["prepare", "dense", "rerank", "select"];

function at(id: string): { x: number; y: number } {
  const node = document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
  const match = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/.exec(node.style.transform);
  return { x: Number(match![1]), y: Number(match![2]) };
}

async function openUser() {
  const view = openStudio("#/studio/search-copy/search", FIXTURES);
  await screen.findByRole("toolbar", { name: "View controls" });
  await waitFor(() => expect(document.querySelectorAll(".react-flow__node")).toHaveLength(STEPS.length));
  return view;
}

const toolbar = () => screen.getByRole("toolbar", { name: "View controls" });

describe("canvas arrange button", () => {
  it("names the arrangement it will apply", async () => {
    await openUser();
    expect(within(toolbar()).getByRole("button", { name: "Arrange vertically" })).toBeInTheDocument();
    expect(within(toolbar()).queryByRole("button", { name: "Arrange horizontally" })).not.toBeInTheDocument();
  });

  it("puts the steps in one column and turns the connection points top and bottom", async () => {
    const { user } = await openUser();
    await user.click(within(toolbar()).getByRole("button", { name: "Arrange vertically" }));
    await waitFor(() => expect(new Set(STEPS.map((id) => at(id).x)).size).toBe(1));
    const ys = STEPS.map((id) => at(id).y);
    expect([...ys].sort((a, b) => a - b)).toEqual(ys);
    expect(new Set(ys).size).toBe(STEPS.length);
    expect(document.querySelectorAll(".react-flow__handle-top").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".react-flow__handle-bottom").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".react-flow__handle-left")).toHaveLength(0);
    expect(within(toolbar()).getByRole("button", { name: "Arrange horizontally" })).toBeInTheDocument();
  });

  it("puts the steps in one row again when arranged horizontally", async () => {
    const { user } = await openUser();
    await user.click(within(toolbar()).getByRole("button", { name: "Arrange vertically" }));
    await user.click(await within(toolbar()).findByRole("button", { name: "Arrange horizontally" }));
    await waitFor(() => expect(new Set(STEPS.map((id) => at(id).y)).size).toBe(1));
    expect(at("prepare").x).toBeLessThan(at("dense").x);
  });

  it("creates no revision, and Save layout stores the direction", async () => {
    const { server, user } = await openUser();
    await user.click(within(toolbar()).getByRole("button", { name: "Arrange vertically" }));
    expect(server.calls.filter((c) => c.method === "POST" && c.path.endsWith("/revisions"))).toHaveLength(0);
    expect(server.calls.filter((c) => c.method === "PUT")).toHaveLength(0);
    await openAllSections(user);
    await user.click(within(runPanel()).getByRole("button", { name: "Save layout" }));
    await waitFor(() => expect(server.last("PUT", "/v1/pipelines/p1/layout")).toBeDefined());
    const layout = (server.last("PUT", "/v1/pipelines/p1/layout")!.body as { layout: { direction: string } }).layout;
    expect(layout.direction).toBe("vertical");
    expect(server.calls.filter((c) => c.method === "POST" && c.path.endsWith("/revisions"))).toHaveLength(0);
  });

  it("opens a layout saved as vertical in the vertical arrangement", async () => {
    const vertical = { ...TEMPLATE_PIPELINE, layout: { ...TEMPLATE_PIPELINE.layout, direction: "vertical" as const } };
    openStudio("#/studio/search-copy/search", { ...FIXTURES, pipelines: [EMPTY_PIPELINE, vertical] });
    expect(await screen.findByRole("button", { name: "Arrange horizontally" })).toBeInTheDocument();
  });

  it("moves the steps for the visit only on a read-only canvas and sends no layout", async () => {
    const { server, user } = openStudio("#/studio/documents/search", { pipelines: FIXTURES.pipelines, revisions: FIXTURES.revisions });
    const button = await screen.findByRole("button", { name: "Arrange vertically" });
    await waitFor(() => expect(document.querySelectorAll(".react-flow__node").length).toBeGreaterThan(1));
    await user.click(button);
    expect(await screen.findByRole("button", { name: "Arrange horizontally" })).toBeInTheDocument();
    const xs = [...document.querySelectorAll<HTMLElement>(".react-flow__node")].map((n) => n.style.transform.match(/translate\((-?[\d.]+)px/)![1]);
    expect(new Set(xs).size).toBe(1);
    expect(server.calls.filter((c) => c.method === "PUT")).toHaveLength(0);
  });
});
