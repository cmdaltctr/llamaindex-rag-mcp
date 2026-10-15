import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafeValue } from "./SafeValue";

describe("SafeValue layout", () => {
  it("stacks each key above its value on narrow screens and uses two columns from sm", () => {
    const { container } = render(<SafeValue value={{ rerank: { enabled: true, top_k: 8192 } }} />);
    const rows = [...container.querySelectorAll("dl > div")];
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row).toHaveClass("grid-cols-1", "sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]");
    }
  });

  it("lets a long value wrap instead of widening the page", () => {
    render(<SafeValue value={{ long: "x".repeat(200) }} />);
    expect(screen.getByText("x".repeat(200))).toHaveClass("[overflow-wrap:anywhere]");
  });

  it("lets a bare value wrap too", () => {
    render(<SafeValue value={{ flag: true }} />);
    expect(screen.getByText("true")).toHaveClass("[overflow-wrap:anywhere]");
  });

  it("renders stored strings as text, never markup", () => {
    const { container } = render(<SafeValue value={{ note: "<img src=x onerror=alert(1)>" }} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });
});
