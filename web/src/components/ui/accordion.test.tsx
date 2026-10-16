import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { LucideIcon } from "lucide-react";
import { describe, expect, it } from "vitest";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "./accordion";

// Lucide icons hide themselves from assistive technology. This icon does not, so the test
// shows the accordion hides the icon and not the icon library.
const TitledIcon = ((props: Record<string, unknown>) => (
  <svg {...props}>
    <title>Decorative</title>
  </svg>
)) as unknown as LucideIcon;

function Fixture() {
  return (
    <Accordion type="multiple">
      <AccordionItem value="one">
        <AccordionTrigger icon={TitledIcon}>Operations</AccordionTrigger>
        <AccordionContent>
          <input aria-label="Search" />
        </AccordionContent>
      </AccordionItem>
      <AccordionItem value="two">
        <AccordionTrigger>Nodes</AccordionTrigger>
        <AccordionContent>Node list</AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

describe("Accordion", () => {
  it("reports the open state on the header and shows the content", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    const header = screen.getByRole("button", { name: "Operations" });
    expect(header).toHaveAttribute("aria-expanded", "false");
    await user.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("region", { name: "Operations" })).toBeVisible();
  });

  it("moves focus to the next header with the Down arrow", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    screen.getByRole("button", { name: "Operations" }).focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("button", { name: "Nodes" })).toHaveFocus();
  });

  it("keeps closed content out of the page", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    expect(screen.queryByLabelText("Search")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Operations" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Operations" }));
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
  });

  it("keeps the title as the name when a header shows an icon", () => {
    render(<Fixture />);
    const header = screen.getByRole("button", { name: "Operations" });
    const icon = header.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("allows several sections open and renders the header as a level-2 heading", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    await user.click(screen.getByRole("button", { name: "Operations" }));
    await user.click(screen.getByRole("button", { name: "Nodes" }));
    expect(screen.getByRole("button", { name: "Operations" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Nodes" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(2);
  });

  it("toggles with Enter and Space", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    const header = screen.getByRole("button", { name: "Nodes" });
    header.focus();
    await user.keyboard("{Enter}");
    expect(header).toHaveAttribute("aria-expanded", "true");
    await user.keyboard(" ");
    expect(header).toHaveAttribute("aria-expanded", "false");
  });
});
