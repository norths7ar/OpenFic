import { IconButton, TextField } from "@radix-ui/themes";
import { Search, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export function ProjectNavSearch({
  value,
  onChange,
  placeholder,
  onExpandedChange,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  onExpandedChange?: (expanded: boolean) => void;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const expand = (next: boolean) => {
    setExpanded(next);
    onExpandedChange?.(next);
  };
  return expanded || value ? (
    <TextField.Root
      size="2"
      value={value}
      placeholder={placeholder}
      aria-label={placeholder}
      autoFocus
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onChange("");
          expand(false);
        }
      }}
    >
      <TextField.Slot>
        <Search size={16} />
      </TextField.Slot>
      <TextField.Slot>
        <IconButton
          size="1"
          variant="ghost"
          aria-label={t("common.close")}
          onClick={() => {
            onChange("");
            expand(false);
          }}
        >
          <X size={14} />
        </IconButton>
      </TextField.Slot>
    </TextField.Root>
  ) : (
    <IconButton
      size="2"
      variant="ghost"
      aria-label={placeholder}
      onClick={() => expand(true)}
    >
      <Search size={16} />
    </IconButton>
  );
}
