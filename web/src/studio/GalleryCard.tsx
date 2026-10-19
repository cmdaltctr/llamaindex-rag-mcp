import { useId, type ReactNode } from "react";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";

interface GalleryCardProps {
  /** The title of the card. It names the card group, so tests and screen readers find the card by it. */
  title: string;
  /** Replaces the plain title, for example a title with a rename pencil. `title` still names the card. */
  heading?: ReactNode;
  /** A line between the title and the description, for example a grey ID. */
  subtitle?: ReactNode;
  /** Shown under the title. Nothing renders when it is empty. */
  description: string;
  /** A label shown beside the title, for example a `Badge`. */
  badge?: ReactNode;
  /** Extra content between the description and the action, for example a field. */
  children?: ReactNode;
  /** The actions of the card. */
  action: ReactNode;
}

/** A gallery card: a title, a description and its actions. */
export function GalleryCard({ title, heading, subtitle, description, badge, children, action }: GalleryCardProps) {
  const titleId = useId();
  return (
    <Card role="group" {...(heading === undefined ? { "aria-labelledby": titleId } : { "aria-label": title })}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {heading ?? <CardTitle id={titleId}>{title}</CardTitle>}
          {badge}
        </div>
        {subtitle}
        {description === "" ? null : <CardDescription>{description}</CardDescription>}
      </CardHeader>
      {children}
      <CardFooter className="flex-wrap">{action}</CardFooter>
    </Card>
  );
}
