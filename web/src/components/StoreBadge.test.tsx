import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StoreBadge } from "./StoreBadge";

const LANCE = { name: "lancedb", label: "LanceDB" };

describe("StoreBadge", () => {
  it("shows the label beside a decorative logo named after the backend", () => {
    const { container } = render(<StoreBadge store={LANCE} />);
    expect(screen.getByText("LanceDB")).toBeInTheDocument();
    const logo = container.querySelector("img");
    expect(logo).toHaveAttribute("alt", "");
    expect(logo?.getAttribute("src")).toMatch(/integrations\/vector-stores\/lancedb\.png$/);
  });

  it("gives every logo the same fixed box so row heights never change", () => {
    const { container } = render(<StoreBadge store={{ name: "chroma", label: "ChromaDB" }} />);
    const logo = container.querySelector("img");
    expect(logo).toHaveClass("size-full", "object-contain");
    expect(logo).toHaveAttribute("width", "20");
    expect(logo).toHaveAttribute("height", "20");
    expect(logo?.parentElement).toHaveClass("size-5", "shrink-0");
  });

  it("puts every logo on a light tile so dark logos stay visible in the dark theme", () => {
    const { container } = render(<StoreBadge store={LANCE} />);
    expect(container.querySelector("img")?.parentElement).toHaveClass("bg-white");
  });

  it("drops a missing logo and keeps the label", () => {
    const { container } = render(<StoreBadge store={{ name: "unknown", label: "Unknown DB" }} />);
    fireEvent.error(container.querySelector("img") as HTMLImageElement);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("Unknown DB")).toBeInTheDocument();
  });
});
