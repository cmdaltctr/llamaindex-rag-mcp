import { Settings2 } from "lucide-react";
import { createContext, useContext, type KeyboardEvent, type SyntheticEvent } from "react";
import type { EffectiveControl, OperationDescriptor } from "../api/pipelines";
import { Button } from "../components/ui/button";
import { Popover } from "../components/ui/popover";
import type { Draft } from "./graph";
import { StepSettingsFields } from "./StepSettingsFields";

/** What a step card needs to edit its own step. The flow surface provides it, so node data stays plain. */
export interface StepEdit {
  draft: Draft;
  controls: Record<string, EffectiveControl[]>;
  onChange: (change: (draft: Draft) => Draft) => void;
  readOnly: boolean;
  /** Selects the step and opens Step settings. Absent: the panel shows no link. */
  onOpenStepSettings?: (nodeId: string) => void;
}

export const StepEditContext = createContext<StepEdit | null>(null);

interface StepCardSettingsProps {
  nodeId: string;
  title: string;
  operation: OperationDescriptor | undefined;
  /** Set on Embed chunks only: the model the card names. */
  model?: { name: string | null };
}

// Events in the portalled panel still bubble through React to the card. Stop them, so typing and
// clicking never select, drag or remove the step. Escape must reach the document, where the popover closes.
const stop = (event: SyntheticEvent) => event.stopPropagation();
const stopKeys = (event: KeyboardEvent) => {
  if (event.key !== "Escape") event.stopPropagation();
};

/** The settings button of a step card and the small panel it opens next to the card (design D3). */
export function StepCardSettings({ nodeId, title, operation, model }: StepCardSettingsProps) {
  const edit = useContext(StepEditContext);
  return (
    <Popover
      slot="step-card-settings"
      width={320}
      trigger={(props) => (
        <Button
          {...props}
          variant="ghost"
          size="icon-xs"
          aria-label={`Settings for ${title}`}
          className="nodrag nopan -me-1 -mt-0.5 shrink-0"
          onClick={(event) => {
            event.stopPropagation();
            props.onClick();
          }}
          onKeyDown={stopKeys}
        >
          <Settings2 aria-hidden="true" />
        </Button>
      )}
    >
      {({ close }) => (
        <div className="flex flex-col gap-3" onClick={stop} onPointerDown={stop} onMouseDown={stop} onDoubleClick={stop} onKeyDown={stopKeys}>
          <h3 className="text-ui font-semibold">{title}</h3>
          {model && (
            <p>
              Model: {model.name ? <code className="font-mono text-code">{model.name}</code> : "unknown"}{" "}
              <span className="text-muted-foreground">(change it in Step settings)</span>
            </p>
          )}
          {edit && operation ? (
            <StepSettingsFields draft={edit.draft} nodeId={nodeId} operation={operation} controls={edit.controls} onChange={edit.onChange} readOnly={edit.readOnly} />
          ) : (
            !model && <p className="text-muted-foreground">No settings</p>
          )}
          {edit?.onOpenStepSettings && (
            <Button
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => {
                close();
                edit.onOpenStepSettings?.(nodeId);
              }}
            >
              Open in Step settings
            </Button>
          )}
        </div>
      )}
    </Popover>
  );
}
