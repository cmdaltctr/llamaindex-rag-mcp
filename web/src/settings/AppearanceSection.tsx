import { ThemeSelect } from "../components/ThemeControls";

/** The theme choice. The top bar shows the same control and the same stored value. */
export function AppearanceSection() {
  return (
    <section aria-labelledby="settings-appearance" className="flex flex-col gap-3">
      <h2 id="settings-appearance" className="text-section-title font-semibold">
        Appearance
      </h2>
      <p className="text-meta text-muted-foreground">System follows your operating system. The choice stays in this browser.</p>
      <div>
        <ThemeSelect />
      </div>
    </section>
  );
}
