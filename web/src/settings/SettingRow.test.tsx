import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { renderWithProviders } from "../test/providers";
import { SOURCE_WORDS, sourceText } from "./connectionWords";
import { KeySettingRow, SettingRow, type KeySettingRowProps, type SettingRowProps } from "./SettingRow";

const BINARY = "/opt/homebrew/bin/llama-server";

function row(overrides: Partial<SettingRowProps> = {}) {
  const props: SettingRowProps = {
    label: "Program path",
    value: BINARY,
    source: "config-file",
    pending: false,
    error: null,
    onSave: vi.fn(),
    onRetry: vi.fn(),
    ...overrides,
  };
  renderWithProviders(<SettingRow {...props} />);
  return props;
}

function keyRow(overrides: Partial<KeySettingRowProps> = {}) {
  const props: KeySettingRowProps = {
    label: "OpenRouter key",
    set: true,
    last4: "a1b2",
    source: "keychain",
    keychain: "available",
    keyFile: "secrets/openrouter.key",
    envVar: "OPENROUTER_API_KEY",
    pending: false,
    error: null,
    onSave: vi.fn(),
    onRemove: vi.fn(),
    onRetry: vi.fn(),
    ...overrides,
  };
  renderWithProviders(<KeySettingRow {...props} />);
  return props;
}

describe("source words", () => {
  const words: [string, string][] = [
    ["env", "Set in the environment. Change it there."],
    ["dotenv", "Set in .env. Change it there."],
    ["config-file", "Saved in settings (omrs.jsonc)"],
    ["keychain", "in system keychain"],
    ["key-file", "from key file"],
    ["default", "default"],
    ["none", "not set"],
    ["init", "set when the server started"],
  ];

  it.each(words)("words %s as %s", (source, text) => {
    expect(SOURCE_WORDS[source]).toBe(text);
    expect(sourceText(source)).toBe(text);
  });

  it("adds the detail after the words", () => {
    expect(sourceText("key-file", "secrets/openrouter.key")).toBe("from key file secrets/openrouter.key");
  });

  it("never prints the legacy saved word for an unknown source", () => {
    expect(sourceText("mystery")).toBe("mystery");
  });

  it.each(words)("shows the %s words in a row", (source, text) => {
    row({ source });
    expect(screen.getByText(text)).toBeInTheDocument();
  });
});

describe("SettingRow", () => {
  it("shows the value and source and no input until Edit", () => {
    row();
    expect(screen.getByText(BINARY)).toBeInTheDocument();
    expect(screen.getByText("Saved in settings (omrs.jsonc)")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("opens the input filled with the value in force", async () => {
    row();
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit Program path" }));
    expect(screen.getByRole("textbox", { name: "Program path" })).toHaveValue(BINARY);
  });

  it("shows a default value with the word default", () => {
    row({ label: "Ollama address", value: "http://localhost:11434", source: "default" });
    expect(screen.getByText("http://localhost:11434")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
  });

  it("shows Not set for an empty value and opens an empty input on Edit", async () => {
    row({ value: "", source: "default" });
    expect(screen.getByText("Not set")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Edit Program path" }));
    expect(screen.getByRole("textbox", { name: "Program path" })).toHaveValue("");
  });

  it.each(["env", "dotenv"])("offers no Edit when the source is %s and names the variable", (source) => {
    row({ source, detail: "LLAMACPP_SERVER_MODEL" });
    expect(screen.queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.getByText(/LLAMACPP_SERVER_MODEL/)).toBeInTheDocument();
  });

  it("is read-only and says why when a reason is given", () => {
    row({ readOnlyReason: "A credentials session is needed to change this." });
    expect(screen.queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.getByText("A credentials session is needed to change this.")).toBeInTheDocument();
  });

  it("saves the typed text, then closes the input when the save is done", async () => {
    const user = userEvent.setup();
    const props = row({ onSave: vi.fn((_text: string, done: () => void) => done()) });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    const input = screen.getByRole("textbox", { name: "Program path" });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.clear(input);
    await user.type(input, "/usr/local/bin/llama-server");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(props.onSave).toHaveBeenCalledWith("/usr/local/bin/llama-server", expect.any(Function));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("keeps the input open when the save does not finish", async () => {
    const user = userEvent.setup();
    row({ onSave: vi.fn() });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    await user.type(screen.getByRole("textbox", { name: "Program path" }), "x");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("textbox", { name: "Program path" })).toBeInTheDocument();
  });

  it("drops the typed text on Cancel and fills the input again on the next Edit", async () => {
    const user = userEvent.setup();
    const props = row();
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    await user.type(screen.getByRole("textbox", { name: "Program path" }), "zzz");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    expect(screen.getByRole("textbox", { name: "Program path" })).toHaveValue(BINARY);
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("offers Use default only for a file value", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn((done: () => void) => done());
    row({ onClear });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    await user.click(screen.getByRole("button", { name: "Use default" }));
    expect(onClear).toHaveBeenCalledOnce();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("offers no Use default for a default value", async () => {
    const user = userEvent.setup();
    row({ source: "default", onClear: vi.fn() });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    expect(screen.queryByRole("button", { name: "Use default" })).not.toBeInTheDocument();
  });

  it("refuses a value that fails the check, names the rule and does not call onSave", async () => {
    const user = userEvent.setup();
    const validate = (text: string) => (Number(text) < 2048 ? "Enter 2,048 to 262,144." : null);
    const props = row({ label: "Context window (tokens)", value: "16384", inputType: "number", validate });
    await user.click(screen.getByRole("button", { name: "Edit Context window (tokens)" }));
    const input = screen.getByRole("spinbutton", { name: "Context window (tokens)" });
    await user.clear(input);
    await user.type(input, "1000");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText("Enter 2,048 to 262,144.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(props.onSave).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, "4096");
    expect(screen.queryByText("Enter 2,048 to 262,144.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(props.onSave).toHaveBeenCalledWith("4096", expect.any(Function));
  });

  it("tells the parent the typed text while the input is open and null when it closes", async () => {
    const user = userEvent.setup();
    const onTyped = vi.fn();
    row({ onTyped });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    await user.type(screen.getByRole("textbox", { name: "Program path" }), "x");
    expect(onTyped).toHaveBeenLastCalledWith(`${BINARY}x`);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onTyped).toHaveBeenLastCalledWith(null);
  });

  it("shows the server message of a refused save and a Reload action for a conflict", async () => {
    const user = userEvent.setup();
    const message = "omrs.jsonc changed on disk. Reload to see the new values.";
    row({ error: new ApiError("http", "x", "/v1/x", 409, { status: "error", message }) });
    await user.click(screen.getByRole("button", { name: "Edit Program path" }));
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
});

describe("KeySettingRow", () => {
  it("summarises a keychain key with Replace and Remove and no input", () => {
    keyRow();
    expect(screen.getByText("Key set · ending a1b2 · in system keychain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace OpenRouter key" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove OpenRouter key" })).toBeInTheDocument();
    expect(screen.queryByLabelText("OpenRouter key")).not.toBeInTheDocument();
  });

  it("offers no button for a key from .env", () => {
    keyRow({ source: "dotenv" });
    expect(screen.getByText("Key set · ending a1b2 · Set in .env. Change it there.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers no button for a key from the environment", () => {
    keyRow({ source: "env" });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers Replace and no Remove for a key file, and names the file", () => {
    keyRow({ source: "key-file", detail: "secrets/openrouter.key" });
    expect(screen.getByText("Key set · ending a1b2 · from key file secrets/openrouter.key")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace OpenRouter key" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
  });

  it("leaves out the ending when the server sent none", () => {
    keyRow({ last4: null });
    expect(screen.getByText("Key set · in system keychain")).toBeInTheDocument();
  });

  it("opens an empty key input on Replace and saves the trimmed key", async () => {
    const user = userEvent.setup();
    const props = keyRow({ onSave: vi.fn((_key: string, done: () => void) => done()) });
    await user.click(screen.getByRole("button", { name: "Replace OpenRouter key" }));
    const input = screen.getByLabelText("OpenRouter key");
    expect(input).toHaveValue("");
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Save key" })).toBeDisabled();
    await user.type(input, "  sk-new-key  ");
    await user.click(screen.getByRole("button", { name: "Save key" }));
    expect(props.onSave).toHaveBeenCalledWith("sk-new-key", expect.any(Function));
    expect(screen.queryByLabelText("OpenRouter key")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-new-key")).not.toBeInTheDocument();
  });

  it("tells the parent the typed key while the input is open and null when it closes", async () => {
    const user = userEvent.setup();
    const onTyped = vi.fn();
    keyRow({ onTyped });
    await user.click(screen.getByRole("button", { name: "Replace OpenRouter key" }));
    await user.type(screen.getByLabelText("OpenRouter key"), "ab");
    expect(onTyped).toHaveBeenLastCalledWith("ab");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onTyped).toHaveBeenLastCalledWith(null);
  });

  it("cancels a Replace without saving", async () => {
    const user = userEvent.setup();
    const props = keyRow();
    await user.click(screen.getByRole("button", { name: "Replace OpenRouter key" }));
    await user.type(screen.getByLabelText("OpenRouter key"), "abc");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("OpenRouter key")).not.toBeInTheDocument();
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("removes a keychain key", async () => {
    const props = keyRow();
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove OpenRouter key" }));
    expect(props.onRemove).toHaveBeenCalledOnce();
  });

  it("shows a key input with the placeholder and hint when no key is set", () => {
    keyRow({ set: false, last4: null, source: "none" });
    expect(screen.getByLabelText("OpenRouter key")).toHaveAttribute("placeholder", "Paste key (saved to the system keychain)");
    expect(screen.getByText("Or put it in secrets/openrouter.key")).toBeInTheDocument();
    expect(screen.queryByText(/Key set/)).not.toBeInTheDocument();
  });

  it("marks an optional key and shows no error", () => {
    keyRow({ set: false, last4: null, source: "none", required: false });
    expect(screen.getByText("Optional")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("with no keychain and no key, says so, names the file and variable, and offers no input", () => {
    keyRow({ set: false, last4: null, source: "none", keychain: "unavailable" });
    expect(screen.getByText(/No system keychain is available/)).toHaveTextContent("secrets/openrouter.key");
    expect(screen.getByText(/No system keychain is available/)).toHaveTextContent("OPENROUTER_API_KEY");
    expect(screen.queryByLabelText("OpenRouter key")).not.toBeInTheDocument();
  });
});
