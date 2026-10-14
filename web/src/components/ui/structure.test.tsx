import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";
import { Separator } from "./separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table";

describe("Card", () => {
  it("is flat: a 1px border and the panel radius, with no shadow", () => {
    render(
      <Card data-testid="card">
        <CardHeader>
          <CardTitle>Collection</CardTitle>
          <CardDescription>12 files</CardDescription>
        </CardHeader>
        <CardContent>Body</CardContent>
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("border", "rounded-panel", "bg-card");
    expect(card.className).not.toMatch(/shadow/);
    expect(screen.getByRole("heading", { name: "Collection", level: 3 })).toBeInTheDocument();
  });
});

describe("Separator", () => {
  it("is decorative by default and a real separator when asked", () => {
    const { rerender } = render(<Separator data-testid="rule" />);
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    rerender(<Separator decorative={false} orientation="vertical" />);
    expect(screen.getByRole("separator")).toHaveAttribute("aria-orientation", "vertical");
  });
});

describe("Table", () => {
  it("renders a semantic table inside a keyboard-scrollable wrapper", () => {
    render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>run-1</TableCell>
            <TableCell>Completed</TableCell>
          </TableRow>
        </TableBody>
      </Table>,
    );
    const table = screen.getByRole("table");
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "run-1" })).toBeInTheDocument();
    expect(table.parentElement).toHaveAttribute("tabindex", "0");
    expect(table.parentElement).toHaveClass("overflow-x-auto");
  });
});
