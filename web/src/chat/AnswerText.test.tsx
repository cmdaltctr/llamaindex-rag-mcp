import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Citation, Evidence } from "../api/documents";
import { TooltipProvider } from "../components/ui/tooltip";
import { AnswerText, ClaimList } from "./AnswerText";

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

  it("turns each ordinal of a grouped marker [1, 3] into its own citation button", () => {
    const { container } = show("Shown in two papers [1, 3, 7].", [cite(1), cite(2), cite(3)]);
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Citation 3" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(container).toHaveTextContent("papers [1, 3, 7].");
  });

  it("does not turn [n] inside inline code or a code block into a button", () => {
    show("Index `a[1]` here.\n\n```\nb[2]\n```");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("a[1]")).toBeInTheDocument();
  });
});

describe("ClaimList", () => {
  function claims(items: { claim: string; verdict: string; ordinals: number[] }[]) {
    const citations = [cite(1), cite(2)];
    const evidence = citations.map((c) => ({ ...c, text: `Evidence ${c.ordinal}` })) as Evidence[];
    return render(
      <TooltipProvider>
        <ClaimList claims={items} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
      </TooltipProvider>,
    );
  }

  it("renders inline code in a claim as code, with no backticks left", () => {
    const { container } = claims([{ claim: "Run `omrg --version` first.", verdict: "unsupported", ordinals: [1] }]);
    expect(screen.getByText("omrg --version").tagName).toBe("CODE");
    expect(container).not.toHaveTextContent("`");
  });

  it("renders the cited ordinal of a claim as a citation button", () => {
    claims([{ claim: "A claim.", verdict: "unsupported", ordinals: [1, 2] }]);
    expect(screen.getByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Citation 2" })).toBeInTheDocument();
    expect(screen.getByText(/unsupported/)).toBeInTheDocument();
  });

  it("keeps a marker with no matching citation as text", () => {
    claims([{ claim: "A claim.", verdict: "unsupported", ordinals: [9] }]);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText(/cites \[9\]/)).toBeInTheDocument();
  });

  it("shows a claim that is only a code fence as written", () => {
    const { container } = claims([{ claim: "```", verdict: "unsupported", ordinals: [1] }]);
    expect(container.querySelector("pre")).toBeNull();
    expect(container).toHaveTextContent("```");
  });

  it("keeps one list item per claim and the list label", () => {
    claims([
      { claim: "One.", verdict: "unsupported", ordinals: [1] },
      { claim: "Two.", verdict: "contradicted", ordinals: [2] },
    ]);
    const list = screen.getByRole("list", { name: "Claims that failed verification" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("AnswerText spacing", () => {
  const SAMPLE = "## Steps\n\nFirst paragraph.\n\nSecond paragraph.\n\n1. one\n2. two\n   - nested a\n   - nested b\n\n- alpha\n- beta\n\nLast paragraph.";

  it("puts every top-level block in one spaced column", () => {
    const { container } = show(SAMPLE);
    const column = container.firstElementChild as HTMLElement;
    expect(column).toHaveClass("flex", "flex-col", "gap-4");
    const tags = Array.from(column.children).map((el) => el.tagName);
    expect(tags).toEqual(["H2", "P", "P", "OL", "UL", "P"]);
  });

  it("spaces list items from each other", () => {
    const { container } = show(SAMPLE);
    for (const list of container.querySelectorAll("ul, ol")) expect(list).toHaveClass("flex", "flex-col", "gap-2");
  });

  it("spaces a nested list and a second paragraph from the text above them in an item", () => {
    const { container } = show("1. item text\n   - nested\n\n2. second\n\n   continued paragraph");
    for (const item of container.querySelectorAll("li")) expect(item).toHaveClass("[&>*+*]:mt-2");
  });

  it("separates a heading from the paragraph that follows it", () => {
    const { container } = show("### Title\n\nBody text.");
    const column = container.firstElementChild as HTMLElement;
    expect(column.children[0]!.tagName).toBe("H3");
    expect(column.children[1]!.tagName).toBe("P");
    expect(column).toHaveClass("gap-4");
  });
});

describe("citation buttons and copied text", () => {
  it("lets the reader select a citation in the answer, so a copy keeps the number", () => {
    show("A claim [1].");
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("select-text");
  });

  it("lets the reader select a citation in a failed claim", () => {
    const citations = [cite(1)];
    const evidence = citations.map((c) => ({ ...c, text: "Evidence 1" })) as Evidence[];
    render(
      <TooltipProvider>
        <ClaimList claims={[{ claim: "A claim.", verdict: "unsupported", ordinals: [1] }]} citations={citations} evidence={evidence} collection="documents" onShowChunk={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("select-text");
  });

  it("keeps a citation close to the punctuation after it", () => {
    show("A claim [1].");
    expect(screen.getByRole("button", { name: "Citation 1" })).toHaveClass("px-0");
  });
});

describe("AnswerText list items", () => {
  const LOOSE = "- first item [1]\n\n- second item\n\n1. one\n\n2. two";

  it("does not keep the newline text between an item's children, so the bullet shares a line with its text", () => {
    const { container } = show(LOOSE);
    for (const item of container.querySelectorAll("li")) {
      // A loose item holds a newline text node before its paragraph. With pre-line it renders as a line break.
      expect(item).not.toHaveClass("whitespace-pre-line");
      expect(item.firstElementChild?.tagName).toBe("P");
    }
  });

  it("colours the bullet and number markers with the primary label colour", () => {
    const { container } = show(LOOSE);
    for (const list of container.querySelectorAll("ul, ol")) expect(list).toHaveClass("marker:text-primary-label");
  });
});
