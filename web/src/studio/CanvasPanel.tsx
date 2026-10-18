import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "../components/ui/accordion";
import { Button } from "../components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { cn } from "../lib/utils";
import { SECTIONS, type SectionId } from "./panelSections";

interface CanvasPanelProps {
  /** The selected node, if any. A new selection opens Node settings. */
  selectedNode: string | null;
  /** Counts runs started from the panel. A change opens Revision and run. A run that exists at load does not. */
  runStarts: number;
  sections: Record<SectionId, ReactNode>;
  /** Hides the panel without unmounting it, so its open sections survive canvas full screen. */
  hidden?: boolean;
}

const add = (open: string[], id: SectionId) => (open.includes(id) ? open : [...open, id]);

/**
 * The one floating panel of the canvas: six accordion sections in a card that
 * collapses to an icon rail. From the `lg` breakpoint the layer floats over
 * the flow surface; below it the card stacks under the surface and shows its
 * sections whatever the collapsed state is. Collapse is CSS only, so closed
 * content stays mounted state-wise and no effect resets it. Mount with the
 * canvas, so state starts fresh for each pipeline.
 */
export function CanvasPanel({ selectedNode, runStarts, sections, hidden = false }: CanvasPanelProps) {
  const [open, setOpen] = useState<string[]>(() => (selectedNode === null ? ["operations"] : ["operations", "node-settings"]));
  const [collapsed, setCollapsed] = useState(false);
  const [seenSelection, setSeenSelection] = useState(selectedNode);
  const [seenRuns, setSeenRuns] = useState(runStarts);
  const layer = useRef<HTMLElement>(null);
  const focusTarget = useRef<string | null>(null);

  // Compared during render, never in an effect, so a restored selection or an
  // earlier run does not open anything on reload.
  if (selectedNode !== seenSelection) {
    setSeenSelection(selectedNode);
    if (selectedNode !== null) setOpen((current) => add(current, "node-settings"));
  }
  if (runStarts !== seenRuns) {
    setSeenRuns(runStarts);
    setOpen((current) => add(current, "run"));
  }

  useEffect(() => {
    const target = focusTarget.current;
    if (target === null) return;
    focusTarget.current = null;
    layer.current?.querySelector<HTMLElement>(`[data-focus="${target}"]`)?.focus();
  });

  function collapse() {
    focusTarget.current = "expand";
    setCollapsed(true);
  }

  function expand(section?: SectionId) {
    focusTarget.current = section ? `section:${section}` : "collapse";
    if (section) setOpen((current) => add(current, section));
    setCollapsed(false);
  }

  return (
    <aside
      ref={layer}
      aria-label="Canvas panel"
      hidden={hidden}
      className={cn("pointer-events-none lg:absolute lg:inset-0 lg:flex lg:items-start lg:justify-end lg:gap-2 lg:p-3", hidden && "hidden lg:hidden")}
    >
      <div
        className={cn(
          "pointer-events-auto flex w-full flex-col overflow-y-auto border-t border-border bg-card lg:max-h-full lg:w-[22rem] lg:rounded-panel lg:border lg:shadow-floating",
          collapsed && "lg:hidden",
        )}
      >
        <div className="hidden justify-end border-b border-border p-1.5 lg:flex">
          <Button variant="ghost" size="icon-sm" aria-label="Collapse panel" data-focus="collapse" className="hidden lg:inline-flex" onClick={collapse}>
            <PanelRightClose aria-hidden="true" />
          </Button>
        </div>
        <Accordion type="multiple" value={open} onValueChange={setOpen}>
          {SECTIONS.map((section) => (
            <AccordionItem key={section.id} value={section.id}>
              <AccordionTrigger icon={section.icon} data-focus={`section:${section.id}`}>
                {section.title}
              </AccordionTrigger>
              <AccordionContent>{sections[section.id]}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
      {collapsed && (
        <TooltipProvider>
          <div
            role="group"
            aria-label="Panel sections"
            className="pointer-events-auto hidden flex-col items-center gap-1 rounded-panel border border-border bg-card p-1.5 shadow-floating lg:flex"
          >
            <Button variant="ghost" size="icon-sm" aria-label="Expand panel" data-focus="expand" onClick={() => expand()}>
              <PanelRightOpen aria-hidden="true" />
            </Button>
            {SECTIONS.map((section) => {
              const Icon = section.icon;
              const isOpen = open.includes(section.id);
              return (
                <Tooltip key={section.id}>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={isOpen ? `${section.title}, open` : section.title}
                      className={cn("rounded-control", isOpen && "bg-selection")}
                      onClick={() => expand(section.id)}
                    >
                      <Icon aria-hidden="true" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">{section.title}</TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </TooltipProvider>
      )}
    </aside>
  );
}
