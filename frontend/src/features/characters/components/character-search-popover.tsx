import "./character-search-popover.css";
import { Box, Flex, IconButton, Popover, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ChevronsUpDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CharacterSearchResult } from "@/lib/character.types";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";

import { searchCharacters } from "../lib/character-api";

interface CharacterSearchPopoverProps {
  projectId: string;
  query: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigateToMatch: (characterId: string) => void;
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
        className="character-search-popover__match"
      >
        {text.slice(idx, idx + query.length)}
      </mark>,
    );
    lastIndex = idx + query.length;
    idx = lowerText.indexOf(lowerQuery, lastIndex);
  }

  if (lastIndex < text.length)
    parts.push(<span key={`t-${lastIndex}`}>{text.slice(lastIndex)}</span>);

  return <>{parts}</>;
}

function CharacterResultGroup({
  result,
  query,
  collapsed,
  onToggle,
  onNavigateToMatch,
}: {
  result: CharacterSearchResult;
  query: string;
  collapsed: boolean;
  onToggle: () => void;
  onNavigateToMatch: (characterId: string) => void;
}) {
  const ChevronIcon = collapsed ? ChevronRight : ChevronDown;

  return (
    <Box>
      <Flex
        align="center"
        gap="1"
        onClick={onToggle}
        className="character-search-popover__group-heading"
        onMouseEnter={(event) => {
          event.currentTarget.style.background = "var(--gray-a3)";
        }}
        onMouseLeave={(event) => {
          event.currentTarget.style.background = "transparent";
        }}
      >
        <ChevronIcon
          size={14}
          className="character-search-popover__group-chevron"
        />
        <Text
          size="2"
          weight="bold"
          className="character-search-popover__group-title"
        >
          {result.characterName}
        </Text>
        <Box className="character-search-popover__match-count">
          <Text
            size="1"
            className="character-search-popover__count-label"
          >
            {result.matches.length}
          </Text>
        </Box>
      </Flex>

      {!collapsed && (
        <Box className="character-search-popover__matches">
          <Box className="character-search-popover__group-guide" />
          {result.matches.map((match) => (
            <Box
              key={`${result.characterId}-${match.lineNumber}-${match.lineText}`}
              onClick={() => onNavigateToMatch(result.characterId)}
              className="character-search-popover__match-row"
              onMouseEnter={(event) => {
                event.currentTarget.style.background = "var(--gray-a3)";
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.background = "transparent";
              }}
            >
              <Text
                size="1"
                className="character-search-popover__match-text"
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

export function CharacterSearchPopover({
  projectId,
  query,
  open,
  onOpenChange,
  onNavigateToMatch,
  children,
}: CharacterSearchPopoverProps) {
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
    queryKey: projectDataQueryKeys.characters.search(projectId, debouncedQuery),
    queryFn: () => searchCharacters(projectId, debouncedQuery),
    enabled: !!projectId && debouncedQuery.trim().length > 0 && open,
    staleTime: 0,
  });

  const handleToggleCharacter = useCallback((characterId: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(characterId)) next.delete(characterId);
      else next.add(characterId);
      return next;
    });
  }, []);

  const handleToggleAll = useCallback(() => {
    if (!data) return;
    setAllCollapsed((prev) => {
      const next = !prev;
      setCollapsedIds(next ? new Set(data.results.map((result) => result.characterId)) : new Set());
      return next;
    });
  }, [data]);

  const handleNavigate = useCallback(
    (characterId: string) => {
      onNavigateToMatch(characterId);
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
      <Popover.Trigger className="character-search-popover__trigger">{children}</Popover.Trigger>
      <Popover.Content
        align="start"
        side="bottom"
        sideOffset={4}
        onOpenAutoFocus={(event) => event.preventDefault()}
        className="character-search-popover__content"
      >
        <Box className="character-search-popover__results">
          {debouncedQuery.trim().length === 0 ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("characters.searchPlaceholder")}
              </Text>
            </Box>
          ) : isLoading ? (
            <Box p="4">
              <Text
                size="2"
                color="gray"
                align="center"
              >
                {t("characters.searching")}
              </Text>
            </Box>
          ) : hasResults ? (
            <>
              <Flex
                align="center"
                justify="between"
                className="character-search-popover__header"
              >
                <Text
                  size="1"
                  color="gray"
                >
                  {t("characters.searchResultSummary", {
                    characters: data.totalCharacters,
                    matches: data.totalMatches,
                  })}
                </Text>
                <IconButton
                  variant="ghost"
                  size="1"
                  onClick={handleToggleAll}
                  title={allCollapsed ? t("characters.expandAll") : t("characters.collapseAll")}
                >
                  <ChevronsUpDown size={14} />
                </IconButton>
              </Flex>
              {data.results.map((result) => (
                <CharacterResultGroup
                  key={result.characterId}
                  result={result}
                  query={debouncedQuery}
                  collapsed={collapsedIds.has(result.characterId)}
                  onToggle={() => handleToggleCharacter(result.characterId)}
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
                {t("characters.noCharactersFound")}
              </Text>
            </Box>
          )}
        </Box>
      </Popover.Content>
    </Popover.Root>
  );
}
