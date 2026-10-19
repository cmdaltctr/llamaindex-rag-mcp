import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Citation, Evidence } from "../api/documents";
import { TooltipProvider } from "../components/ui/tooltip";
import { AnswerText } from "./AnswerText";

function cite(ordinal: number): Citation {
  return {
    ordinal, chunk_id: `c-${ordinal}`, chunk_ids: [`c-${ordinal}`], source_id: "sid-1", source_version: "v7",
    source: "/srv/docs/paper.pdf", source_chunk_index: ordinal, score: 0.5, score_kind: "reranker_sigmoid_v1",
  } as Citation;
}

function show(text: string, citations: Citation[] = [cite(1), cite(2)]) {
  const evidence = citations.map((c) => ({ ...c, text: `Evidence ${c.ordinal}` })) as Evidence[];
  return render(
    <TooltipProvider>
      <AnswerText text={text} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
    </TooltipProvider>,
  );
}

describe("AnswerText markdown", () => {
  it("renders **bold** and *italic* as elements, with no asterisks left", () => {
    const { container } = show("This is **strong** and *soft* text.");
    expect(container.querySelector("strong")).toHaveTextContent("strong");
    expect(container.querySelector("em")).toHaveTextContent("soft");
    expect(container).not.toHaveTextContent("*");
  });

  it("renders headings at their own level", () => {
    show("# Title\n\n## Section\n\n### Part\n\nBody");
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Section" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Part" })).toBeInTheDocument();
  });

  it("renders unordered and ordered lists with one item per entry", () => {
    show("- alpha\n- beta\n\n1. first\n2. second\n3. third");
    const lists = screen.getAllByRole("list");
    expect(lists).toHaveLength(2);
    expect(within(lists[0]!).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["alpha", "beta"]);
    expect(lists[1]!.tagName).toBe("OL");
    expect(within(lists[1]!).getAllByRole("listitem")).toHaveLength(3);
  });

  it("renders inline code and a fenced code block with its language and exact text", () => {
    const { container } = show("Use `top_k` here.\n\n```python\nx = 1\nprint(x)\n```");
    expect(screen.getByText("top_k").tagName).toBe("CODE");
    const block = container.querySelector("pre code");
    expect(block).not.toBeNull();
    expect(block!.textContent).toBe("x = 1\nprint(x)\n");
    expect(block).toHaveClass("language-python");
  });

  it("renders a GFM table", () => {
    show("| a | b |\n| - | - |\n| 1 | 2 |");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "a" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2" })).toBeInTheDocument();
  });

  it("does not render raw HTML or script from the model", () => {
    const { container } = show('Hi <b>raw</b><script>window.__x = 1</script><img src="x" onerror="1">');
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders a link as a safe external anchor and drops a javascript: href", () => {
    show("[docs](https://example.com/a) and [bad](javascript:alert(1))");
    const good = screen.getByRole("link", { name: "docs" });
    expect(good).toHaveAttribute("href", "https://example.com/a");
    expect(good).toHaveAttribute("target", "_blank");
    expect(good).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.queryByRole("link", { name: "bad" })).toBeNull();
  });
});

describe("AnswerText citations inside markdown", () => {
  it("keeps [n] as a citation button inside bold, a list item and a heading", () => {
    show("## Result [1]\n\n- item **strong [2]**");
    expect(screen.getByRole("heading", { level: 2 })).toContainElement(screen.getByRole("button", { name: "Citation 1" }));
    expect(screen.getByRole("listitem")).toContainElement(screen.getByRole("button", { name: "Citation 2" }));
    expect(screen.getByRole("button", { name: "Citation 2" }).closest("strong")).not.toBeNull();
  });

  it("leaves a marker with no matching citation as text", () => {
    show("Known [1] and unknown [7].");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText(/unknown \[7\]/)).toBeInTheDocument();
  });

  it("does not turn [n] inside inline code or a code block into a button", () => {
    show("Index `a[1]` here.\n\n```\nb[2]\n```");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("a[1]")).toBeInTheDocument();
  });
});
