import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../api/ApiProvider";
import { installIntegration, type IntegrationInstall, type InstallType } from "../api/integrations";
import { integrationInstallQuery, queryKeys } from "../api/queries";

export interface InstallControl {
  /** The running or last install of this launch, once read. */
  install: IntegrationInstall | undefined;
  /** True while an install runs or a start request is in flight. Every Install button is then disabled. */
  busy: boolean;
  /** The extra whose start request is in flight. */
  starting: string | null;
  /** Starts an install of `extra`. */
  start: (extra: string) => void;
  /** The refused start of `extra`, or `null`. */
  refusal: (extra: string) => unknown;
  /** Clears a refusal and reads the catalogue again. */
  recheck: () => void;
}

/**
 * The install state and the start action of the Integrations page.
 *
 * The status is read once when the page opens, and only when the server is a
 * `uv tool` install, because no other install type can run an install. It is
 * then polled every second only while an install runs (`integrationInstallQuery`).
 * The one read on open finds an install that started before the page loaded.
 */
export function useIntegrationInstall(installType: InstallType | undefined): InstallControl {
  const api = useApi();
  const queryClient = useQueryClient();
  const status = useQuery({ ...integrationInstallQuery(api), enabled: installType === "uv-tool" });
  const mutation = useMutation({
    mutationFn: (extra: string) => installIntegration(api, extra),
    onSuccess: (install) => queryClient.setQueryData(queryKeys.integrationInstall(), install),
  });
  const starting = mutation.isPending ? (mutation.variables ?? null) : null;
  return {
    install: status.data,
    busy: status.data?.state === "running" || starting !== null,
    starting,
    start: (extra) => mutation.mutate(extra),
    refusal: (extra) => (mutation.isError && mutation.variables === extra ? mutation.error : null),
    recheck: () => {
      mutation.reset();
      void queryClient.invalidateQueries({ queryKey: queryKeys.integrations() });
    },
  };
}
