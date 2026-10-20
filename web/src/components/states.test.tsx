import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inbox } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { EmptyState } from "./EmptyState";
import { ErrorNotice } from "./ErrorNotice";
import { NotFound } from "./NotFound";
import { PageHeader } from "./PageHeader";

const RAW = "Expected JSON from /v1/collections but received text/html (status 200). <html>boom</html>";

describe("EmptyState", () => {
  it("shows an icon, one sentence and one action", () => {
    const { container } = render(<EmptyState icon={Inbox} message="No projects yet." action={<a href="#/knowledge-base">Add a source</a>} />);
    expect(screen.getByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add a source" })).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("PageHeader", () => {
  it("lets a long unbroken title wrap instead of widening the page", () => {
    const title = `Run ${"a".repeat(32)}`;
    render(<PageHeader title={title} />);
    expect(screen.getByRole("heading", { level: 1, name: title })).toHaveClass("[overflow-wrap:anywhere]");
  });

  it("keeps the heading focusable for the shell", () => {
    render(<PageHeader title="Home" />);
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toHaveAttribute("tabindex", "-1");
  });
});

describe("NotFound", () => {
  it("names what is missing and links back to its picker", () => {
    render(<NotFound what="collection" name="papers" backHref="#/knowledge-base" backLabel="Choose a project" />);
    expect(screen.getByText(/collection .papers. could not be found/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a project" })).toHaveAttribute("href", "#/knowledge-base");
  });
});

describe("ErrorNotice", () => {
  function notice(error: unknown, props: Partial<Parameters<typeof ErrorNotice>[0]> = {}) {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    return render(<ErrorNotice error={error} {...props} />);
  }

  it("shows one friendly line and a Retry action for an unreachable server", async () => {
    const onRetry = vi.fn();
    notice(new ApiError("network", RAW, "/v1/collections"), { onRetry });
    expect(screen.getByRole("alert")).toHaveTextContent("The local server is not reachable.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it.each([
    new ApiError("not-json", RAW, "/v1/collections", 200),
    new ApiError("invalid-json", RAW, "/v1/collections", 200),
    new ApiError("http", RAW, "/v1/collections", 500),
    new ApiError("http", RAW, "/v1/collections", 403),
    new Error(RAW),
  ])("never shows parser or status text (%#)", (error) => {
    notice(error, { onRetry: () => undefined });
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).not.toContain("Expected JSON");
    expect(text).not.toContain("text/html");
    expect(text).not.toContain("<html>");
    expect(text).not.toMatch(/status \d+/i);
    expect(text).not.toContain("/v1/");
  });

  it("links a missing resource back to its picker", () => {
    notice(new ApiError("http", RAW, "/v1/collections/x", 404), { backHref: "#/knowledge-base" });
    expect(screen.getByRole("link", { name: "Go back" })).toHaveAttribute("href", "#/knowledge-base");
  });

  it("offers the file chooser for an oversized upload", async () => {
    const onChooseFile = vi.fn();
    notice(new ApiError("http", RAW, "/v1/uploads", 413), { onChooseFile });
    await userEvent.setup().click(screen.getByRole("button", { name: "Choose another file" }));
    expect(onChooseFile).toHaveBeenCalled();
  });

  it.each([
    ["network", new ApiError("network", RAW, "/v1/x")],
    ["not-json", new ApiError("not-json", RAW, "/v1/x", 200)],
    ["http 500", new ApiError("http", RAW, "/v1/x", 500)],
    ["http 404", new ApiError("http", RAW, "/v1/x", 404)],
    ["http 413", new ApiError("http", RAW, "/v1/x", 413)],
    ["http 403", new ApiError("http", RAW, "/v1/x", 403)],
    ["invalid-path", new ApiError("invalid-path", RAW, "/v1/x")],
    ["a plain error", new Error(RAW)],
  ])("always offers one action, even when the caller wires none (%s)", (_name, error) => {
    notice(error);
    const alert = screen.getByRole("alert");
    expect(alert.querySelectorAll("button, a")).toHaveLength(1);
  });

  it("falls back to Home for a missing resource when no picker is given", () => {
    notice(new ApiError("http", RAW, "/v1/x", 404));
    expect(screen.getByRole("link", { name: "Go to Home" })).toHaveAttribute("href", "#/home");
  });

  it("falls back to reloading the page for a retry nobody wired", () => {
    notice(new ApiError("http", RAW, "/v1/x", 500));
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
  });

  it("offers a reload for a refused session", () => {
    notice(new ApiError("http", RAW, "/v1/session", 401));
    expect(screen.getByRole("alert")).toHaveTextContent(/reload the page\. if that fails, run omrg web open/i);
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeInTheDocument();
  });
});
