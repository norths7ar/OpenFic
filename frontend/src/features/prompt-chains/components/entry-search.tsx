import "./entry-search.css";
import { Box, Flex, IconButton, Popover, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ChevronsUpDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { PromptEntrySearchResult } from "@/lib/prompt-chain.types";

import { searchPromptChainVersionEntries } from "../lib/prompt-chain-api";

interface EntrySearchProps {
  promptId: string;
  versionId: string;
  query: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateToMatch: (entryId: string) => void;
  children: React.ReactNode;
}

function highlightText(text: string, query: string): React.ReactNode {
  if (!query) return text;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let index = lowerText.indexOf(lowerQuery, lastIndex);

  while (index !== -1) {
    if (index > lastIndex) {
      parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex, index)}</span>);
    }
    parts.push(
      <mark
        key={`m-${index}`}
        className="entry-search__match"
      >
        {text.slice(index, index + query.length)}
      </mark>,
    );
    lastIndex = index + query.length;
    index = lowerText.indexOf(lowerQuery, lastIndex);
  }

  if (lastIndex < text.length)
    parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex)}</span>);

  return <>{parts}</>;
}

function EntryResultGroup({
  result,
  query,
  collapsed,
  onToggle,
  onNavigateToMatch,
}: {
  result: PromptEntrySearchResult;
  query: string;
  collapsed: boolean;
  onToggle: () => void;
  onNavigateToMatch: (entryId: string) => void;
}) {
  const ChevronIcon = collapsed ? ChevronRight : ChevronDown;

  return (
    <Box>
      <Flex
        align="center"
        gap="1"
        onClick={onToggle}
        className="entry-search__group-heading"
        onMouseEnter={(event) => {
          event.currentTarget.style.background = "var(--gray-a3)";
        }}
        onMouseLeave={(event) => {
          event.currentTarget.style.background = "transparent";
        }}
      >
        <ChevronIcon
          size={14}
          className="entry-search__group-chevron"
        />
        <Text
          size="2"
          weight="bold"
          className="entry-search__group-title"
        >
          {result.entryName}
        </Text>
        <Box className="entry-search__match-count">
          <Text
            size="1"
            className="entry-search__count-label"
          >
            {result.matches.length}
          </Text>
        </Box>
      </Flex>

      {!collapsed && (
        <Box className="entry-search__matches">
          <Box className="entry-search__group-guide" />
          {result.matches.map((match) => (
            <Box
              key={`${result.entryId}-${match.lineNumber}-${match.lineText}`}
              onClick={() => onNavigateToMatch(result.entryId)}
              className="entry-search__match-row"
              onMouseEnter={(event) => {
                event.currentTarget.style.background = "var(--gray-a3)";
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.background = "transparent";
              }}
            >
              <Text
                size="1"
                className="entry-search__match-text"
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

export function EntrySearch({
  promptId,
  versionId,
  query,
  open,
  onOpenChange,
  onNavigateToMatch,
  children,
}: EntrySearchProps) {
  const { t } = useTranslation();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [allCollapsed, setAllCollapsed] = useState(false);
  const previousOpenRef = useRef(open);

  useEffect(() => {
    if (open && !previousOpenRef.current && query.trim()) {
      setDebouncedQuery(query);
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
    }
    previousOpenRef.current = open;
  }, [open, query]);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(query);
      setCollapsedIds(new Set());
      setAllCollapsed(false);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [open, query]);

  const { data, isLoading } = useQuery({
    queryKey: ["prompt-chain-entry-search", promptId, versionId, debouncedQuery],
    queryFn: () => searchPromptChainVersionEntries(promptId, versionId, debouncedQuery),
    enabled: !!promptId && !!versionId && debouncedQuery.trim().length > 0 && open,
    staleTime: 0,
  });

  const handleToggleEntry = useCallback((entryId: string) => {
    setCollapsedIds((previous) => {
      const next = new Set(previous);
      if (next.has(entryId)) next.delete(entryId);
      else next.add(entryId);
      return next;
    });
  }, []);

  const handleToggleAll = useCallback(() => {
    if (!data) return;
    setAllCollapsed((previous) => {
      const next = !previous;
      setCollapsedIds(next ? new Set(data.results.map((result) => result.entryId)) : new Set());
      return next;
    });
  }, [data]);

  const handleNavigate = useCallback(
    (entryId: string) => {
      onNavigateToMatch(entryId);
      onOpenChange(false);
    },
    [onNavigateToMatch, onOpenChange],
  );

  const hasResults = data && data.results.length > 0;

  return (
    <Popover.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Popover.Trigger className="entry-search__trigger">{children}</Popover.Trigger>
      <Popover.Content
        align="start"
        side="bottom"
        sideOffset={4}
        onOpenAutoFocus={(event) => event.preventDefault()}
        className="entry-search__content"
      >
        <Box className="entry-search__results">
          {debouncedQuery.trim().length === 0 ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("promptChains.searchPlaceholder")}
              </Text>
            </Box>
          ) : isLoading ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("promptChains.searching")}
              </Text>
            </Box>
          ) : hasResults ? (
            <>
              <Flex
                align="center"
                justify="between"
                className="entry-search__header"
              >
                <Text
                  size="1"
                  color="gray"
                >
                  {t("promptChains.searchResultSummary", {
                    entries: data.totalEntries,
                    matches: data.totalMatches,
                  })}
                </Text>
                <IconButton
                  variant="ghost"
                  size="1"
                  onClick={handleToggleAll}
                  title={allCollapsed ? t("promptChains.expandAll") : t("promptChains.collapseAll")}
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
                {t("promptChains.noEntriesFound")}
              </Text>
            </Box>
          )}
        </Box>
      </Popover.Content>
    </Popover.Root>
  );
}
