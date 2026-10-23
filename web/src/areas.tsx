import { ChatView } from "./chat/ChatView";
import { ExperimentsView } from "./experiments/ExperimentsView";
import { HomeView } from "./home/HomeView";
import { IntegrationsView } from "./integrations/IntegrationsView";
import { KnowledgeBaseView } from "./knowledge-base/KnowledgeBaseView";
import { SettingsView } from "./settings/SettingsView";
import { StudioView } from "./studio/StudioView";
import type { Route } from "./lib/routes";

/** Renders the view for a route. Each area replaces its entry here when its view lands. */
export function renderArea(route: Route) {
  switch (route.area) {
    case "home":
      return <HomeView />;
    case "knowledge-base":
      return <KnowledgeBaseView />;
    case "chat":
      return <ChatView />;
    case "experiments":
      return <ExperimentsView runId={route.runId} />;
    case "integrations":
      return <IntegrationsView entry={route.entry} />;
    case "settings":
      return <SettingsView />;
    case "studio":
      return <StudioView profileId={route.profileId} purpose={route.purpose} />;
  }
}
