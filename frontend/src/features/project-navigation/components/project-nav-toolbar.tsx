import { Box, Flex } from "@radix-ui/themes";
import type { ReactNode } from "react";

import "./project-nav.css";

interface ProjectNavToolbarProps {
  search: ReactNode;
  sort?: ReactNode;
  create?: ReactNode;
  more?: ReactNode;
  searchExpanded?: boolean;
}

export function ProjectNavToolbar({
  search,
  sort,
  create,
  more,
  searchExpanded,
}: ProjectNavToolbarProps) {
  return (
    <Flex
      className="project-nav-toolbar"
      align="center"
      gap="1"
    >
      <Box className="project-nav-toolbar-search">{search}</Box>
      {!searchExpanded && sort}
      {!searchExpanded && create}
      {!searchExpanded && more}
    </Flex>
  );
}
