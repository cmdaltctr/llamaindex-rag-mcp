import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it } from "vitest";
import { EMPTY_PIPELINE, inspector, TEMPLATE_PIPELINE, TEMPLATE_REVISION, UNUSED_PROFILES } from "./test/helpers";
import { mockReactFlow } from "./test/mockReactFlow";
import { openStudio } from "./test/render";

beforeAll(mockReactFlow);

const FIXTURES = { pipelines: [EMPTY_PIPELINE, TEMPLATE_PIPELINE], revisions: [TEMPLATE_REVISION] };
const step = (id: string) => document.querySelector<HTMLElement>(`.react-flow__node[data-id="${id}"]`)!;
const panel = () => document.querySelector<HTMLElement>("[data-slot='step-card-settings']");
const stepSettingsHeader = () => screen.getByRole("button", { name: "Step settings" });

async function open(hash: string, options = {}) {
  const view = openStudio(hash, { ...FIXTURES, ...options });
  await waitFor(() => expect(step("rerank")).not.toBeNull());
  return view;
}

describe("the card settings panel on the canvas", () => {
  it("opens Step settings for its step with Open in Step settings", async () => {
    const { user } = await open("#/studio/search-copy/search", { profiles: UNUSED_PROFILES });
    expect(stepSettingsHeader()).toHaveAttribute("aria-expanded", "false");
    await user.click(within(step("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    await user.click(within(panel()!).getByRole("button", { name: "Open in Step settings" }));
    expect(panel()).toBeNull();
    expect(stepSettingsHeader()).toHaveAttribute("aria-expanded", "true");
    expect(within(inspector()).getByRole("heading", { name: "Cross-encoder rerank" })).toBeInTheDocument();
    expect(stepSettingsHeader()).toHaveFocus();
  });

  it("opens Step settings again when the step is already selected", async () => {
    const { user } = await open("#/studio/search-copy/search", { profiles: UNUSED_PROFILES });
    await user.click(within(step("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    await user.click(within(panel()!).getByRole("button", { name: "Open in Step settings" }));
    await user.click(stepSettingsHeader());
    expect(stepSettingsHeader()).toHaveAttribute("aria-expanded", "false");
    await user.click(within(step("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    await user.click(within(panel()!).getByRole("button", { name: "Open in Step settings" }));
    expect(stepSettingsHeader()).toHaveAttribute("aria-expanded", "true");
  });

  it("disables every control on a built-in profile", async () => {
    const { user } = await open("#/studio/documents/search");
    await user.click(within(step("rerank")).getByRole("button", { name: "Settings for Cross-encoder rerank" }));
    expect(within(panel()!).getByRole("checkbox", { name: "Bypass this step" })).toBeDisabled();
    for (const radio of within(panel()!).getAllByRole("radio")) expect(radio).toBeDisabled();
  });
});
