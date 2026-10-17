import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CanvasPanel } from "./CanvasPanel";
import { SECTIONS } from "./panelSections";

function Harness({ selectedNode = null, runStarts = 0 }: { selectedNode?: string | null; runStarts?: number }) {
  const [collection, setCollection] = useState("papers");
  return (
    <CanvasPanel
      selectedNode={selectedNode}
      runStarts={runStarts}
      sections={{
        "pipeline-settings": <input aria-label="Collection" value={collection} onChange={(event) => setCollection(event.target.value)} />,
        operations: <button type="button">Add dense</button>,
        nodes: <p>Node list</p>,
        connect: <p>Connect form</p>,
        run: <p>Run controls</p>,
        "node-settings": <p>Node form</p>,
      }}
    />
  );
}

const header = (title: string) => screen.getByRole("button", { name: title });
const rail = () => screen.getByRole("group", { name: "Panel sections" });
const railButton = (name: string) => within(rail()).getByRole("button", { name });
const card = () => screen.getByRole("complementary", { name: "Canvas panel" }).firstElementChild as HTMLElement;

describe("CanvasPanel sections", () => {
  it("shows six headers in order, each with an icon hidden from assistive technology", () => {
    render(<Harness />);
    const names = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(names).toEqual(SECTIONS.map((section) => section.title));
    for (const section of SECTIONS) {
      const icon = header(section.title).querySelector("svg");
      expect(icon).not.toBeNull();
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("opens only Operations at load", () => {
    render(<Harness />);
    for (const section of SECTIONS) {
      expect(header(section.title)).toHaveAttribute("aria-expanded", String(section.id === "operations"));
    }
  });

  it("also opens Step settings at load when a node is already selected", () => {
    render(<Harness selectedNode="dense" />);
    const open = SECTIONS.filter((section) => header(section.title).getAttribute("aria-expanded") === "true");
    expect(open.map((section) => section.id)).toEqual(["operations", "node-settings"]);
  });

  it("names each open content region by its title", () => {
    render(<Harness />);
    expect(screen.getByRole("region", { name: "Operations" })).toHaveTextContent("Add dense");
    expect(screen.queryByRole("region", { name: "Revision and run" })).not.toBeInTheDocument();
  });

  it("keeps two sections open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(header("Pipeline settings"));
    expect(header("Pipeline settings")).toHaveAttribute("aria-expanded", "true");
    expect(header("Operations")).toHaveAttribute("aria-expanded", "true");
  });

  it("opens Step settings when a node is selected after load", () => {
    const { rerender } = render(<Harness />);
    expect(header("Step settings")).toHaveAttribute("aria-expanded", "false");
    rerender(<Harness selectedNode="dense" />);
    expect(header("Step settings")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Step settings" })).toHaveTextContent("Node form");
  });

  it("opens Revision and run when a run starts from the panel, not at load", () => {
    const { rerender } = render(<Harness runStarts={0} />);
    expect(header("Revision and run")).toHaveAttribute("aria-expanded", "false");
    rerender(<Harness runStarts={1} />);
    expect(header("Revision and run")).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps an edited title when Pipeline settings is closed and opened again", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(header("Pipeline settings"));
    await user.type(screen.getByLabelText("Collection"), " copy");
    await user.click(header("Pipeline settings"));
    expect(screen.queryByLabelText("Collection")).not.toBeInTheDocument();
    await user.click(header("Pipeline settings"));
    expect(screen.getByLabelText("Collection")).toHaveValue("papers copy");
  });

  it("toggles a header with Enter and Space", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    header("Connect ports").focus();
    await user.keyboard("{Enter}");
    expect(header("Connect ports")).toHaveAttribute("aria-expanded", "true");
    await user.keyboard(" ");
    expect(header("Connect ports")).toHaveAttribute("aria-expanded", "false");
  });
});

describe("CanvasPanel rail", () => {
  it("collapses to six rail buttons and an expand button, and moves focus to the expand button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    const sectionButtons = within(rail())
      .getAllByRole("button")
      .filter((button) => button.getAttribute("aria-label") !== "Expand panel");
    expect(sectionButtons).toHaveLength(6);
    const expand = screen.getByRole("button", { name: "Expand panel" });
    expect(expand).toHaveFocus();
    expect(card()).toHaveClass("lg:hidden");
  });

  it("moves focus back to the collapse button when the expand button is used", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    await user.click(screen.getByRole("button", { name: "Expand panel" }));
    expect(screen.getByRole("button", { name: "Collapse panel" })).toHaveFocus();
    expect(screen.queryByRole("group", { name: "Panel sections" })).not.toBeInTheDocument();
  });

  it("expands from a rail button, opens its section and focuses its header", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    await user.click(railButton("Connect ports"));
    expect(header("Connect ports")).toHaveAttribute("aria-expanded", "true");
    expect(header("Connect ports")).toHaveFocus();
    expect(card()).not.toHaveClass("lg:hidden");
  });

  it("does not close a section that is already open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    await user.click(railButton("Operations, open"));
    expect(header("Operations")).toHaveAttribute("aria-expanded", "true");
  });

  it("highlights open sections and adds ', open' to their name", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    const open = railButton("Operations, open");
    expect(open).toHaveClass("bg-selection");
    for (const section of SECTIONS.filter((candidate) => candidate.id !== "operations")) {
      const button = railButton(section.title);
      expect(button).not.toHaveClass("bg-selection");
    }
  });

  it("stays collapsed when a node is selected and highlights Step settings", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    rerender(<Harness selectedNode="dense" />);
    expect(screen.getByRole("button", { name: "Expand panel" })).toBeInTheDocument();
    expect(card()).toHaveClass("lg:hidden");
    expect(railButton("Step settings, open")).toHaveClass("bg-selection");
    await user.click(railButton("Step settings, open"));
    expect(screen.getByRole("region", { name: "Step settings" })).toHaveTextContent("Node form");
  });

  it("keeps the open sections and the draft over a collapse and expand round trip", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(header("Pipeline settings"));
    await user.type(screen.getByLabelText("Collection"), "!");
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    await user.click(screen.getByRole("button", { name: "Expand panel" }));
    expect(header("Pipeline settings")).toHaveAttribute("aria-expanded", "true");
    expect(header("Operations")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Collection")).toHaveValue("papers!");
  });

  it("shows a tooltip with the section title on a rail button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    act(() => railButton("Connect ports").focus());
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Connect ports");
  });

  it("uses the keyboard to open a section from the rail", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    railButton("Revision and run").focus();
    await user.keyboard("{Enter}");
    expect(header("Revision and run")).toHaveAttribute("aria-expanded", "true");
    expect(header("Revision and run")).toHaveFocus();
  });

  it("collapses only from lg up: the card never carries lg:hidden while expanded, and the rail is hidden below lg", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(card()).not.toHaveClass("lg:hidden");
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    expect(rail()).toHaveClass("hidden", "lg:flex");
    expect(screen.getByRole("button", { name: "Collapse panel", hidden: true })).toHaveClass("hidden", "lg:inline-flex");
  });

  it("lets pointer events through the layer outside the card and the rail", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const layer = screen.getByRole("complementary", { name: "Canvas panel" });
    expect(layer).toHaveClass("pointer-events-none");
    expect(card()).toHaveClass("pointer-events-auto", "lg:shadow-floating");
    await user.click(screen.getByRole("button", { name: "Collapse panel" }));
    expect(rail()).toHaveClass("pointer-events-auto", "shadow-floating");
  });
});
