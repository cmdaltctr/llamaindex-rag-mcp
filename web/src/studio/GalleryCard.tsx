import { useId, type ReactNode } from "react";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "../components/ui/card";

interface GalleryCardProps {
  title: string;
  description: string;
  /** A label shown beside the title, for example a `Badge`. */
  badge?: ReactNode;
  /** Extra content between the description and the action, for example a field. */
  children?: ReactNode;
  /** The one action of the card. */
  action: ReactNode;
}

/** A gallery card: a title, a description and one action. */
export function GalleryCard({ title, description, badge, children, action }: GalleryCardProps) {
  const titleId = useId();
  return (
    <Card role="group" aria-labelledby={titleId}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle id={titleId}>{title}</CardTitle>
          {badge}
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {children}
      <CardFooter>{action}</CardFooter>
    </Card>
  );
}
