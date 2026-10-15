import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../test/providers";
import { experimentsServer } from "../test/experimentsServer";
import { FAILED_RESULT } from "../test/runFixtures";
import { EvidenceInspector } from "./EvidenceInspector";

function setup(outputs = FAILED_RESULT.outputs!) {
  const server = experimentsServer();
  const user = userEvent.setup();
  const view = renderWithProviders(<EvidenceInspector runId="r1" outputs={outputs} fallbackCollection="docs" />, { fetchImpl: server.fetchImpl });
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

  it("opens the full chunk in the shared chunk viewer, as text", async () => {
    const { server, user } = setup();
    const row = within(table("reranked")).getAllByRole("row")[1]!;
    await user.click(within(row).getByRole("button", { name: "Show full chunk c-long" }));
    const dialog = await screen.findByRole("dialog", { name: "Stored chunk" });
    await waitFor(() => expect(dialog).toHaveTextContent("Full text of c-long <script>alert(1)</script>"));
    expect(server.calls.at(-1)?.path).toBe("/v1/collections/docs/chunks/c-long?window=1");
    expect(document.querySelector("script")).toBeNull();
  });

  it("lists citations with links to their chunks", async () => {
    const { server, user } = setup();
    const citations = screen.getByRole("list", { name: "Citations: answer.citations" });
    expect(citations).toHaveTextContent("[1] notes.md");
    expect(screen.getByText("RRF fuses ranks.")).toBeInTheDocument();
    await user.click(within(citations).getByRole("button", { name: "Show full chunk c-html" }));
    await screen.findByRole("dialog", { name: "Stored chunk" });
    expect(server.calls.at(-1)?.path).toBe("/v1/collections/docs/chunks/c-html?window=1");
  });

  it("masks a secret in an evidence row", () => {
    setup({ rows: [{ chunk_id: "c1", source: "https://u:s3cretpass@host/doc", text: "token is Bearer abcdefghijklmnop", score_kind: "rrf_v1", score: 0.1 }] });
    const row = within(table("rows")).getAllByRole("row")[1]!;
    expect(row).not.toHaveTextContent("s3cretpass");
    expect(row).not.toHaveTextContent("abcdefghijklmnop");
    expect(row).toHaveTextContent("[redacted]");
  });

  it("explains an output it cannot show as rows", () => {
    setup({ results: "RankedEvidence(rows=...)" });
    expect(screen.getByText(/No ranked rows, citations or answers were found/)).toBeInTheDocument();
  });
});
