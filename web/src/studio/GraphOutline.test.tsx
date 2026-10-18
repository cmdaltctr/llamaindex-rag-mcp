import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { fromDocument } from "./graph";
import { GraphOutline } from "./GraphOutline";
import { TEMPLATE_DOC } from "./test/helpers";

function setup() {
  const onSelect = vi.fn();
  const onChange = vi.fn();
  render(<GraphOutline draft={fromDocument(TEMPLATE_DOC, {})} issues={[]} onChange={onChange} onSelect={onSelect} onAnnounce={() => undefined} />);
  return { onSelect, onChange, user: userEvent.setup() };
}

describe("GraphOutline selection", () => {
  it("asks the canvas to centre on a step", async () => {
    const { onSelect, user } = setup();
    await user.click(screen.getByRole("button", { name: /^Node dense/ }));
    expect(onSelect).toHaveBeenCalledWith("dense");
  });

  it("selects a connection without asking the canvas to centre (a connection key is not a step id)", async () => {
    const { onSelect, onChange, user } = setup();
    await user.click(screen.getByRole("button", { name: /^Connection prepare\.query to dense\.query/ }));
    expect(onSelect).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
