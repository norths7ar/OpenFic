import { createContext } from "react";

export const WorkspaceDiscussionContext = createContext<{
  open: boolean;
  toggle: () => void;
} | null>(null);
