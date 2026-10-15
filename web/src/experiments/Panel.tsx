import { useId, type ReactNode } from "react";
import { Card } from "../components/ui/card";

interface PanelProps {
  title: string;
  /** One sentence under the title. */
  description?: string;
  /** Heading level; the view heading is the `h1`. */
  level?: 2 | 3;
  children: ReactNode;
}

/** A named card: its heading names the region for assistive technology. */
export function Panel({ title, description, level = 2, children }: PanelProps) {
  const id = useId();
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={id}>
      <Card>
        <div className="flex flex-col gap-1">
          <Heading id={id} className={level === 2 ? "text-section-title font-semibold" : "text-subsection-title font-semibold"}>
            {title}
          </Heading>
          {description !== undefined ? <p className="text-meta text-muted-foreground">{description}</p> : null}
        </div>
        {children}
      </Card>
    </section>
  );
}
