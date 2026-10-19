import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, hueFor } from "./badge";

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

  describe("hue variant", () => {
    it("hashes the label to a stable hue", () => {
      expect(hueFor("documents")).toBe(hueFor("documents"));
      expect(hueFor("documents")).not.toBe(hueFor("codebase"));
      for (const label of ["documents", "codebase", "retrieve.dense", "", "é"]) {
        const hue = hueFor(label);
        expect(Number.isInteger(hue)).toBe(true);
        expect(hue).toBeGreaterThanOrEqual(0);
        expect(hue).toBeLessThan(360);
      }
    });

    it("pairs the hue with the label text and uses the same hue everywhere", () => {
      render(
        <>
          <Badge variant="hue">documents</Badge>
          <Badge variant="hue" data-testid="again">
            documents
          </Badge>
          <Badge variant="hue">codebase</Badge>
        </>,
      );
      const [first, second] = screen.getAllByText("documents");
      expect(first).toHaveStyle({ "--badge-hue": String(hueFor("documents")) });
      expect(second).toHaveStyle({ "--badge-hue": String(hueFor("documents")) });
      expect(screen.getByText("codebase")).toHaveStyle({ "--badge-hue": String(hueFor("codebase")) });
      expect(screen.getByText("codebase")).toBeVisible();
    });

    it("uses a transparent fill, the text colour as border and a theme-specific lightness", () => {
      render(<Badge variant="hue">documents</Badge>);
      const badge = screen.getByText("documents");
      expect(badge).toHaveClass("bg-transparent", "border-current");
      expect(badge.className).toContain("text-[oklch(0.42_0.13_var(--badge-hue))]");
      expect(badge.className).toContain("dark:text-[oklch(0.8_0.13_var(--badge-hue))]");
    });

    it("takes an explicit hue over the hash", () => {
      render(
        <Badge variant="hue" hue={200}>
          tuned
        </Badge>,
      );
      expect(screen.getByText("tuned")).toHaveStyle({ "--badge-hue": "200" });
    });

    it("sets no hue on a status badge", () => {
      render(<Badge variant="success">ok</Badge>);
      expect(screen.getByText("ok").getAttribute("style")).toBeNull();
    });
  });
});
