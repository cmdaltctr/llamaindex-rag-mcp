import { Plug } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ErrorNotice } from "../components/ErrorNotice";
import { Button } from "../components/ui/button";
import { Check, TextField } from "./fields";
import { pluginStatusLabel } from "./labels";
import { useRegisterPlugin } from "./mutations";

/** Registers an approved manifest and executable. Registration runs no process and installs nothing. */
export function PluginRegisterForm() {
  const register = useRegisterPlugin();
  const [manifestPath, setManifestPath] = useState("");
  const [executablePath, setExecutablePath] = useState("");
  const [approved, setApproved] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const ready = approved && manifestPath.trim() !== "" && executablePath.trim() !== "" && !register.isPending;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setDone(null);
    try {
      const state = await register.mutateAsync({ manifestPath: manifestPath.trim(), executablePath: executablePath.trim(), approved });
      setDone(`Registered ${state.name}: ${pluginStatusLabel(state.status)}. ${state.message}`);
      setApproved(false);
    } catch {
      // The mutation holds the error, which renders below.
    }
  }

  return (
    <form aria-label="Register a plugin" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3 border-t border-border pt-3">
      <h4 className="text-subsection-title font-semibold">Register a plugin</h4>
      <p className="text-meta text-muted-foreground">
        Use the shipped manifest or one below the workspace plugins folder. The executable must be on the server&apos;s PATH or below that folder.
      </p>
      <div className="flex flex-wrap gap-3">
        <TextField label="Manifest path" dir="ltr" value={manifestPath} onChange={setManifestPath} />
        <TextField label="Executable path" dir="ltr" value={executablePath} onChange={setExecutablePath} />
      </div>
      <Check checked={approved} onChange={setApproved}>
        I approve this manifest and executable. Notebooks they open run Python with my permissions.
      </Check>
      <div>
        <Button type="submit" disabled={!ready}>
          <Plug aria-hidden="true" />
          Register plugin
        </Button>
      </div>
      {register.isError ? <ErrorNotice error={register.error} /> : null}
      {done !== null ? (
        <p role="status" className="text-meta [overflow-wrap:anywhere]">
          {done}
        </p>
      ) : null}
    </form>
  );
}
