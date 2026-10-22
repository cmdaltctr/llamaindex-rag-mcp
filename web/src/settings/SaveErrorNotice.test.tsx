import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { createQueryClient } from "../api/queries";
import { renderWithProviders } from "../test/providers";
import { SaveErrorNotice } from "./SaveErrorNotice";

const MESSAGE = "omrs.jsonc changed on disk. Reload to see the new values.";

describe("SaveErrorNotice", () => {
  it("reads the Settings routes again on Reload for a file conflict, then clears the error", async () => {
    const user = userEvent.setup();
    const queryClient = createQueryClient({ retry: false });
    await queryClient.prefetchQuery({ queryKey: ["connections"], queryFn: () => ({}) });
    await queryClient.prefetchQuery({ queryKey: ["settings", "chat"], queryFn: () => ({}) });
    await queryClient.prefetchQuery({ queryKey: ["chats"], queryFn: () => ({}) });
    const onRetry = vi.fn();
    renderWithProviders(<SaveErrorNotice error={new ApiError("http", "x", "/v1/x", 409, { status: "error", message: MESSAGE })} onRetry={onRetry} />, { queryClient });
    expect(screen.getByRole("alert")).toHaveTextContent(MESSAGE);
    await user.click(screen.getByRole("button", { name: "Reload" }));
    expect(queryClient.getQueryState(["connections"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["settings", "chat"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["chats"])?.isInvalidated).toBe(false);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("offers Retry for a refused value and calls onRetry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    renderWithProviders(<SaveErrorNotice error={new ApiError("http", "x", "/v1/x", 400, { status: "error", message: "The program must be an absolute path." })} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The program must be an absolute path.");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
