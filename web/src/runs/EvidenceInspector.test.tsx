import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { EvidenceInspector } from "./EvidenceInspector";
import { FAILED_RESULT, runServer } from "./test/runServer";

function setup(outputs = FAILED_RESULT.outputs!) {
  const server = runServer();
  const user = userEvent.setup();
  const view = render(<EvidenceInspector outputs={outputs} fallbackCollection="docs" fetchImpl={server.fetchImpl} />);
  return { server, user, view };
}

function table(name: string) {
  return screen.getByRole("table", { name: `Ranked rows: ${name}` });
}

describe("evidence inspector", () => {
  it("labels rank and score by score kind", () => {
    setup();
    const reranked = table("reranked");
    expect(within(reranked).getAllByRole("row")[1]).toHaveTextContent("1");
    expect(within(reranked).getAllByRole("row")[1]).toHaveTextContent("Reranker score 0.9123");
    expect(within(reranked).getAllByRole("row")[1]).toHaveTextContent("fused rank 3");
    expect(within(table("fused")).getAllByRole("row")[1]).toHaveTextContent("RRF score 0.03000");
    const sparse = within(table("sparse")).getAllByRole("row")[1]!;
    expect(sparse).toHaveTextContent("Rank only");
    expect(sparse).not.toHaveTextContent("2.000");
    expect(screen.getByText(/not probabilities of correctness/)).toBeInTheDocument();
  });

  it("bounds previews at 100 rows and 4 KiB and says so", () => {
    setup();
    expect(screen.getByText("Showing the first 100 of 130 rows.")).toBeInTheDocument();
    expect(within(table("fused")).getAllByRole("row")).toHaveLength(101);
    const longRow = within(table("reranked")).getAllByRole("row")[1]!;
    expect(longRow).toHaveTextContent("Preview cut at 4 KiB.");
    expect(longRow.textContent!.length).toBeLessThan(4300);
  });

  it("renders stored text as text, never as markup", () => {
    const { view } = setup();
    expect(within(table("reranked")).getByText("<b>bold</b> text")).toBeInTheDocument();
    expect(view.container.querySelector("b")).toBeNull();
  });

  it("opens the full chunk through the protected chunk route", async () => {
    const { server, user, view } = setup();
    const row = within(table("reranked")).getAllByRole("row")[1]!;
    await user.click(within(row).getByRole("button", { name: "Show full chunk c-long" }));
    const chunk = await screen.findByRole("region", { name: "Chunk c-long" });
    await waitFor(() => expect(chunk).toHaveTextContent("Full text of c-long <script>alert(1)</script>"));
    expect(server.calls.at(-1)?.path).toBe("/v1/collections/docs/chunks/c-long?window=0");
    expect(view.container.querySelector("script")).toBeNull();
  });

  it("lists citations with links to their chunks", async () => {
    const { server, user } = setup();
    const citations = screen.getByRole("list", { name: "Citations: answer.citations" });
    expect(citations).toHaveTextContent("[1] notes.md");
    expect(screen.getByText("RRF fuses ranks.")).toBeInTheDocument();
    await user.click(within(citations).getByRole("button", { name: "Show full chunk c-html" }));
    await screen.findByRole("region", { name: "Chunk c-html" });
    expect(server.calls.at(-1)?.path).toBe("/v1/collections/docs/chunks/c-html?window=0");
  });

  it("explains an output it cannot show as rows", () => {
    setup({ results: "RankedEvidence(rows=...)" });
    expect(screen.getByText(/No ranked rows, citations or answers were found/)).toBeInTheDocument();
  });
});
