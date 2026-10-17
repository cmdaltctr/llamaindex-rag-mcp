import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { addNode, emptyDraft } from "./graph";
import { CATALOGUE } from "./test/catalogueFixture";
import { FlowSurface } from "./FlowSurface";

// The pointer work of React Flow cannot run in jsdom. This stand-in records the props
// that FlowSurface hands over, so the test reads what the library would be told.
const captured = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }));
vi.mock("@xyflow/react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@xyflow/react")>()),
  ReactFlow: (props: Record<string, unknown>) => {
    captured.props = props;
    return null;
  },
}));

interface Seen {
  nodesDraggable: boolean;
  nodesConnectable: boolean;
  isValidConnection: (connection: unknown) => boolean;
  onConnect: (connection: unknown) => void;
  onNodesChange: (changes: unknown[]) => void;
  onEdgesChange: (changes: unknown[]) => void;
}

const FITTING = { source: "prepare_query", sourceHandle: "query", target: "dense", targetHandle: "query" };

const props = () => captured.props as unknown as Seen;

function mount(readOnly: boolean) {
  const onChange = vi.fn();
  const onConnect = vi.fn();
  const onRefused = vi.fn();
  // Two steps whose ports fit, so an editable canvas would accept the connection.
  const draft = ["retrieve.prepare_query", "retrieve.dense"].reduce(
    (current, id) => addNode(current, CATALOGUE.find((entry) => entry.operation_id === id)!).draft,
    emptyDraft(),
  );
  const { container } = render(<FlowSurface draft={draft} catalogue={CATALOGUE} issues={[]} onChange={onChange} onConnect={onConnect} onRefused={onRefused} readOnly={readOnly} />);
  return { onChange, onConnect, onRefused, surface: container.firstElementChild as HTMLElement };
}

beforeEach(() => {
  captured.props = null;
});

describe("FlowSurface on a read-only graph", () => {
  it("turns dragging and connecting off and refuses every connection", () => {
    const { onConnect } = mount(true);
    expect(props().nodesDraggable).toBe(false);
    expect(props().nodesConnectable).toBe(false);
    expect(props().isValidConnection(FITTING)).toBe(false);
    props().onConnect(FITTING);
    expect(onConnect).not.toHaveBeenCalled();
  });

  it("passes selection changes on and drops position and remove changes", () => {
    const { onChange } = mount(true);
    props().onNodesChange([{ type: "position", id: "prepare_query", position: { x: 5, y: 5 } }, { type: "remove", id: "prepare_query" }]);
    props().onEdgesChange([{ type: "remove", id: "e" }]);
    expect(onChange).not.toHaveBeenCalled();
    props().onNodesChange([{ type: "select", id: "prepare_query", selected: true }]);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("does not remove the selection on the Delete key", () => {
    const { onChange, surface } = mount(true);
    fireEvent.keyDown(surface, { key: "Delete" });
    fireEvent.keyDown(surface, { key: "Backspace" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("stays fully editable when readOnly is off", () => {
    mount(false);
    expect(props().nodesDraggable).toBe(true);
    expect(props().nodesConnectable).toBe(true);
    expect(props().isValidConnection(FITTING)).toBe(true);
  });

  it("removes the selection on the Delete key and passes position changes on", () => {
    const { onChange, surface } = mount(false);
    fireEvent.keyDown(surface, { key: "Delete" });
    expect(onChange).toHaveBeenCalledTimes(1);
    props().onNodesChange([{ type: "position", id: "prepare_query", position: { x: 5, y: 5 } }]);
    expect(onChange).toHaveBeenCalledTimes(2);
  });
});
