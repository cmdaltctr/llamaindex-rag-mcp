import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChunkView } from "../api/documents";
import { ChunkMetadata } from "./ChunkMetadata";

function chunk(overrides: Partial<ChunkView> = {}): ChunkView {
  return {
    chunk_id: "c-2",
    source_id: "sid-1",
    source_version: "v7",
    source_chunk_index: 1,
    source_chunk_count: 5,
    source: "/srv/docs/paper.pdf",
    page_label: "4",
    text: "x",
    metadata: {
      chunk_id: "c-2",
      source_id: "sid-1",
      source_version: "v7",
      source_chunk_index: 1,
      source_chunk_count: 5,
      page_label: "4",
      file_name: "paper.pdf",
      title: "A paper",
      keywords: ["rag", "lineage"],
      pages: { from: 1, to: 2 },
    },
    ...overrides,
  };
}

describe("ChunkMetadata", () => {
  it("shows the lineage of the chunk", () => {
    render(<ChunkMetadata chunk={chunk()} />);
    const lineage = screen.getByRole("region", { name: "Lineage" });
    expect(within(lineage).getByText("sid-1")).toBeInTheDocument();
    expect(within(lineage).getByText("v7")).toBeInTheDocument();
    expect(within(lineage).getByText(/Chunk 2 of 5, Page 4/)).toBeInTheDocument();
    expect(within(lineage).queryByText("Chunk IDs")).not.toBeInTheDocument();
  });

  it("lists every chunk id when the citation spans more than one chunk", () => {
    render(<ChunkMetadata chunk={chunk()} chunkIds={["c-2", "c-3"]} />);
    const lineage = screen.getByRole("region", { name: "Lineage" });
    expect(within(lineage).getByText("Chunk IDs")).toBeInTheDocument();
    expect(within(lineage).getByText("c-2, c-3")).toBeInTheDocument();
  });

  it("lists the other stored keys sorted by name, with arrays and objects as compact JSON", () => {
    render(<ChunkMetadata chunk={chunk()} />);
    const metadata = screen.getByRole("region", { name: "Metadata" });
    const keys = within(metadata).getAllByRole("term").map((node) => node.textContent);
    expect(keys).toEqual(["file_name", "keywords", "pages", "title"]);
    expect(within(metadata).getByText('["rag","lineage"]')).toBeInTheDocument();
    expect(within(metadata).getByText('{"from":1,"to":2}')).toBeInTheDocument();
    expect(within(metadata).queryByText("source_id")).not.toBeInTheDocument();
  });

  it("cuts a long value and shows all of it on request", async () => {
    const long = "word ".repeat(80).trim();
    render(<ChunkMetadata chunk={chunk({ metadata: { summary: long } })} />);
    const metadata = screen.getByRole("region", { name: "Metadata" });
    expect(within(metadata).queryByText(long)).not.toBeInTheDocument();
    await userEvent.click(within(metadata).getByRole("button", { name: "Show all of summary" }));
    expect(within(metadata).getByText(long)).toBeInTheDocument();
    expect(within(metadata).queryByRole("button", { name: "Show all of summary" })).not.toBeInTheDocument();
  });

  it("says when the chunk has no other metadata", () => {
    render(<ChunkMetadata chunk={chunk({ metadata: {} })} />);
    expect(screen.getByText(/no other metadata/i)).toBeInTheDocument();
  });
});
