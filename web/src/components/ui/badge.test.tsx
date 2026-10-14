import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";

const STATUSES = ["error", "warning", "success", "info"] as const;

describe("Badge", () => {
  it.each(STATUSES)("derives fill, border and text from the %s status colour", (status) => {
    render(<Badge variant={status}>{status}</Badge>);
    const badge = screen.getByText(status);
    expect(badge).toHaveClass(
      `border-status-${status}`,
      `bg-status-${status}/10`,
      `text-status-${status}-label`,
    );
    // Raw status colours fail WCAG AA as text; only the label mix may colour it.
    expect(badge.className).not.toMatch(new RegExp(`(^| )text-status-${status}( |$)`));
  });

  it("shows the status value as text, not colour alone", () => {
    render(<Badge variant="success">Completed</Badge>);
    expect(screen.getByText("Completed")).toBeVisible();
  });

  it("falls back to the neutral variant", () => {
    render(<Badge>Draft</Badge>);
    expect(screen.getByText("Draft")).toHaveClass("bg-secondary", "border-border");
  });

  it("uses the accent tint for the accent variant", () => {
    render(<Badge variant="accent">Documents</Badge>);
    expect(screen.getByText("Documents")).toHaveClass("bg-primary-tint", "text-primary-label");
  });
});
