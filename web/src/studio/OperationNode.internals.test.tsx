import { render } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { CATALOGUE } from "./test/catalogueFixture";
import { mockReactFlow } from "./test/mockReactFlow";

const updateNodeInternals = vi.fn();

vi.mock("@xyflow/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@xyflow/react")>()),
  useUpdateNodeInternals: () => updateNodeInternals,
}));

import { OperationNode, type OperationFlowNode } from "./OperationNode";

beforeAll(mockReactFlow);

function props(direction: "horizontal" | "vertical"): NodeProps<OperationFlowNode> {
  return {
    id: "dense",
    data: {
      nodeId: "dense", operationId: "retrieve.dense", operation: CATALOGUE.find((o) => o.operation_id === "retrieve.dense"), title: "Dense retrieval",
      showNodeId: false, summary: "", settings: [], moreSettings: 0, extraSettings: [], connected: [], enabled: true, issues: [], direction,
    },
    selected: false,
    isConnectable: true,
  } as unknown as NodeProps<OperationFlowNode>;
}

describe("OperationNode handle positions", () => {
  it("tells React Flow to measure the handles again when the direction changes", () => {
    const view = render(<ReactFlowProvider><OperationNode {...props("horizontal")} /></ReactFlowProvider>);
    updateNodeInternals.mockClear();
    view.rerender(<ReactFlowProvider><OperationNode {...props("vertical")} /></ReactFlowProvider>);
    expect(updateNodeInternals).toHaveBeenCalledWith("dense");
  });

  it("does not ask again when the direction is unchanged", () => {
    const view = render(<ReactFlowProvider><OperationNode {...props("vertical")} /></ReactFlowProvider>);
    updateNodeInternals.mockClear();
    view.rerender(<ReactFlowProvider><OperationNode {...props("vertical")} /></ReactFlowProvider>);
    expect(updateNodeInternals).not.toHaveBeenCalled();
  });
});
