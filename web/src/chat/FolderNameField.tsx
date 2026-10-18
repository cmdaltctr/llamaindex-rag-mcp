import { useState } from "react";
import { Input } from "../components/ui/input";

interface FolderNameFieldProps {
  initial: string;
  onSave: (name: string) => void;
  onCancel: () => void;
}

/** An inline name field: Enter saves a name that is not empty, Escape cancels. */
export function FolderNameField({ initial, onSave, onCancel }: FolderNameFieldProps) {
  const [value, setValue] = useState(initial);
  return (
    <Input
      autoFocus
      aria-label="Folder name"
      maxLength={100}
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Escape") onCancel();
        if (event.key === "Enter" && value.trim() !== "") onSave(value.trim());
      }}
      onBlur={onCancel}
    />
  );
}
