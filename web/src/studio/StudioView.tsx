import type { Purpose } from "../lib/routes";
import { CanvasPage } from "./CanvasPage";
import { ProfileGallery } from "./ProfileGallery";

/** The Studio area: the profile gallery, or the canvas of the profile the route names. */
export function StudioView({ profileId, purpose }: { profileId: string | null; purpose: Purpose | null }) {
  return profileId === null ? <ProfileGallery /> : <CanvasPage profileId={profileId} purpose={purpose} />;
}
