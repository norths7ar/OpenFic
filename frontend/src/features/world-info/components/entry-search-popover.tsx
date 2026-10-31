import "./entry-search-popover.css";
import { Box, Flex, IconButton, Popover, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ChevronsUpDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { projectDataQueryKeys } from "@/lib/project-data-query-keys";
import type { WorldInfoEntrySearchResult } from "@/lib/world-info.types";

import { searchWorldInfoEntries } from "../lib/world-info-api";

interface EntrySearchPopoverProps {
  worldInfoId: string;
  query: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateToMatch: (entryId: string, lineNumber: number) => void;
  children: React.ReactNode;
}

function highlightText(text: string, query: string): React.ReactNode {
  if (!query) return text;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  let idx = lowerText.indexOf(lowerQuery, lastIndex);
  while (idx !== -1) {
    if (idx > lastIndex) {
      parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex, idx)}</span>);
    }
    parts.push(
      <mark
        key={`m-${idx}`}
        className="entry-search-popover__match"
      >
        {text.slice(idx, idx + query.length)}
      </mark>,
    );
    lastIndex = idx + query.length;
    idx = lowerText.indexOf(lowerQuery, lastIndex);
  }

  if (lastIndex < text.length) {
    parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex)}</span>);
  }

  return <>{parts}</>;
}

function EntryResultGroup({
  result,
  query,
  collapsed,
  onToggle,
  onNavigateToMatch,
}: {
  result: WorldInfoEntrySearchResult;
  query: string;
  collapsed: boolean;
  onToggle: () => void;
  onNavigateToMatch: (entryId: string, lineNumber: number) => void;
}) {
  const ChevronIcon = collapsed ? ChevronRight : ChevronDown;

  return (
    <Box>
      <Flex
        align="center"
        gap="1"
        onClick={onToggle}
        className="entry-search-popover__group-heading"
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--gray-a3)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
        }}
      >
        <ChevronIcon
          size={14}
          className="entry-search-popover__group-chevron"
        />
        <Text
          size="2"
          weight="bold"
          className="entry-search-popover__group-title"
        >
          {result.entryName}
        </Text>
        <Box className="entry-search-popover__match-count">
          <Text
            size="1"
            className="entry-search-popover__count-label"
          >
            {result.matches.length}
          </Text>
        </Box>
      </Flex>

      {!collapsed && (
        <Box className="entry-search-popover__matches">
          <Box className="entry-search-popover__group-guide" />
          {result.matches.map((match) => (
            <Box
              key={`${result.entryId}-${match.lineNumber}`}
              onClick={() => onNavigateToMatch(result.entryId, match.lineNumber)}
              className="entry-search-popover__match-row"
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--gray-a3)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              <Text
                size="1"
                className="entry-search-popover__match-text"
              >
                {highlightText(match.lineText, query)}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

export function EntrySearchPopover({
  worldInfoId,
  query,
  open,
  onOpenChange,
  onNavigateToMatch,
  children,
}: EntrySearchPopoverProps) {
  const { t } = useTranslation();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [allCollapsed, setAllCollapsed] = useState(false);

  const prevOpenRef = useRef(open);

  useEffect(() => {
    if (open && !prevOpenRef.current && query.trim()) {
      setDebouncedQuery(query);
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    }
    prevOpenRef.current = open;
  }, [open, query]);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(query);
      setCollapsedIds(new Set());
      setAllCollapsed(false);
    }, 300);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, open]);

  const { data, isLoading } = useQuery({
    queryKey: projectDataQueryKeys.worldInfo.search(worldInfoId, debouncedQuery),
    queryFn: () => searchWorldInfoEntries(worldInfoId, debouncedQuery),
    enabled: !!worldInfoId && debouncedQuery.trim().length > 0 && open,
    staleTime: 0,
  });

  const hasResults = data && data.results.length > 0;

  const handleToggleEntry = useCallback((entryId: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(entryId)) {
        next.delete(entryId);
      } else {
        next.add(entryId);
      }
      return next;
    });
  }, []);

  const handleToggleAll = useCallback(() => {
    if (!data) return;
    setAllCollapsed((prev) => {
      const next = !prev;
      if (next) {
        setCollapsedIds(new Set(data.results.map((r) => r.entryId)));
      } else {
        setCollapsedIds(new Set());
      }
      return next;
    });
  }, [data]);

  const handleNavigate = useCallback(
    (entryId: string, lineNumber: number) => {
      onNavigateToMatch(entryId, lineNumber);
      onOpenChange(false);
    },
    [onNavigateToMatch, onOpenChange],
  );

  return (
    <Popover.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Popover.Trigger className="entry-search-popover__trigger">{children}</Popover.Trigger>

      <Popover.Content
        align="start"
        side="bottom"
        sideOffset={4}
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="entry-search-popover__content"
      >
        <Box className="entry-search-popover__results">
          {debouncedQuery.trim().length === 0 ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("worldInfo.searchPlaceholder")}
              </Text>
            </Box>
          ) : isLoading ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("worldInfo.searching")}
              </Text>
            </Box>
          ) : hasResults ? (
            <>
              <Flex
                align="center"
                justify="between"
                className="entry-search-popover__header"
              >
                <Text
                  size="1"
                  color="gray"
                >
                  {t("worldInfo.searchResultSummary", {
                    entries: data.totalEntries,
                    matches: data.totalMatches,
                  })}
                </Text>
                <IconButton
                  variant="ghost"
                  size="1"
                  onClick={handleToggleAll}
                  title={allCollapsed ? t("worldInfo.expandAll") : t("worldInfo.collapseAll")}
                >
                  <ChevronsUpDown size={14} />
                </IconButton>
              </Flex>
              {data.results.map((result) => (
                <EntryResultGroup
                  key={result.entryId}
                  result={result}
                  query={debouncedQuery}
                  collapsed={collapsedIds.has(result.entryId)}
                  onToggle={() => handleToggleEntry(result.entryId)}
                  onNavigateToMatch={handleNavigate}
                />
              ))}
            </>
          ) : (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("worldInfo.noEntriesFound")}
              </Text>
            </Box>
          )}
        </Box>
      </Popover.Content>
    </Popover.Root>
  );
}
