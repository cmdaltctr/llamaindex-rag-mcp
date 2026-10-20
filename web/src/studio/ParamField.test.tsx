import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JsonValue } from "../api/pipelines";
import { ParamField } from "./ParamField";
import { paramFields } from "./schema";
import { CATALOGUE } from "./test/catalogueFixture";

const FILTER = paramFields(CATALOGUE.find((op) => op.operation_id === "retrieve.prepare_query")!).find((field) => field.name === "metadata_filter")!;

function setup(value?: JsonValue) {
  const onChange = vi.fn();
  render(<ParamField field={FILTER} value={value} note={null} onChange={onChange} />);
  const field = screen.getByRole("textbox", { name: "Metadata filter value" });
  return { onChange, field, type: (text: string) => fireEvent.change(field, { target: { value: text } }) };
}

describe("ParamField for a JSON object setting", () => {
  it("shows the saved value as JSON text", () => {
    const { field } = setup({ file_type: "pdf" });
    expect(field).toHaveValue('{"file_type":"pdf"}');
  });

  it("saves a valid JSON object", () => {
    const { onChange, type } = setup();
    type('{"file_type": "pdf"}');
    expect(onChange).toHaveBeenLastCalledWith({ file_type: "pdf" });
  });

  it.each(["{file_type: pdf}", "[1, 2]", "3", "null"])("refuses %s with Enter a JSON object. and does not change the draft", (text) => {
    const { onChange, field, type } = setup({ file_type: "pdf" });
    type(text);
    expect(screen.getByText("Enter a JSON object.")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes the setting when the text is empty", () => {
    const { onChange, type } = setup({ file_type: "pdf" });
    type("  ");
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.queryByText("Enter a JSON object.")).toBeNull();
  });

  it("is disabled on a read-only graph", () => {
    render(<ParamField field={FILTER} value={{ a: 1 }} note={null} disabled onChange={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "Metadata filter value" })).toBeDisabled();
  });
});
