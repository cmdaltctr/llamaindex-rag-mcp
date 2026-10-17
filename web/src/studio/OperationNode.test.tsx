import { render } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import { CATALOGUE } from "./test/catalogueFixture";
import { OperationNode, type OperationFlowNode } from "./OperationNode";

function mount(isConnectable: boolean) {
  const operation = CATALOGUE.find((entry) => entry.operation_id === "retrieve.dense");
  const props = {
    id: "dense",
    data: { nodeId: "dense", operationId: "retrieve.dense", operation, enabled: true, issues: [] },
    selected: false,
    isConnectable,
  } as unknown as NodeProps<OperationFlowNode>;
  const { container } = render(
    <ReactFlowProvider>
      <OperationNode {...props} />
    </ReactFlowProvider>,
  );
  return [...container.querySelectorAll(".react-flow__handle")];
}

describe("OperationNode handles", () => {
  it("drop the connectable state when the canvas is read-only", () => {
    const handles = mount(false);
    expect(handles.length).toBeGreaterThan(0);
    for (const handle of handles) expect(handle).not.toHaveClass("connectable");
  });

  it("stay connectable on an editable canvas", () => {
    const handles = mount(true);
    expect(handles.length).toBeGreaterThan(0);
    for (const handle of handles) expect(handle).toHaveClass("connectable");
  });
});
