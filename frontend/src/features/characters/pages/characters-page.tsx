import { AlertDialog, Box, Button, Flex, IconButton, Tooltip, Text } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, List } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useParams, useSearchParams } from "react-router";

import { useAppShell } from "@/app/app-shell-context";
import { PanelLayoutLoading } from "@/components";
import { toast } from "@/components/toast";
import { AssistantSidebarHost } from "@/features/app-shell/components/assistant-sidebar-host";
import { MobileAppSidebarTrigger } from "@/features/app-shell/components/mobile-app-sidebar-trigger";
import type { AssistantSidebarState } from "@/features/assistant";
import { buildCharacterMentionTag } from "@/features/assistant/lib/mention-text";
import { fetchProjects } from "@/features/projects/lib/project-api";
import { usePersistedPanelLayout } from "@/hooks/use-persisted-panel-layout";
import type { Character, CharacterListItem, CharacterListResponse } from "@/lib/character.types";
import { getPreference, setPreference } from "@/lib/local-db";
import { projectDataQueryKeys } from "@/lib/project-data-query-keys";
import { countTokens } from "@/lib/tiktoken-utils";

import { CharacterEditor } from "../components/character-editor";
import { CharacterList } from "../components/character-list";
import { CharacterProfileDialog } from "../components/character-profile-dialog";
import {
  batchDeleteCharacters,
  createCharacter,
  deleteCharacter,
  fetchCharacter,
  fetchCharactersByProject,
  reorderCharacters,
  updateCharacter,
} from "../lib/character-api";
import { useCharactersStore } from "../store/use-characters-store";
import { shouldShowCharacterEditorLoading } from "./character-editor-loading-state";

import "./characters-page.css";

const LAST_PROJECT_KEY = "characters.lastProjectId";
const LAST_CHARACTER_KEY = "characters.lastCharacterId";
const PANEL_LAYOUT_KEY = "panel-layout.characters";
const PANEL_IDS = ["characters-list", "characters-editor", "characters-right"];
const MotionBox = motion.create(Box);
const MOBILE_SIDEBAR_WIDTH = 320;

function toCharacterListItem(character: Character): CharacterListItem {
  return {
    id: character.id,
    projectId: character.projectId,
    name: character.name,
    imageUrl: character.imageUrl,
    tokenCount: countTokens(character.description),
    isFavorited: character.isFavorited,
    order: character.order,
    isWritingVisible: character.isWritingVisible,
    createdAt: character.createdAt,
    updatedAt: character.updatedAt,
  };
}

function sortCharacters(characters: CharacterListItem[]): CharacterListItem[] {
  return [...characters].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name, "zh-CN"));
}

export function CharactersPage() {
  const { t } = useTranslation();
  const { projectId: projectIdFromRoute } = useParams<{ projectId: string }>();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { isMobile, openAssistantSidebar } = useAppShell();
  const {
    currentProjectId,
    currentCharacterId,
    isListOpen,
    setCurrentProject,
    setCurrentCharacter,
    setListOpen,
  } = useCharactersStore();
  const [profileCharacter, setProfileCharacter] = useState<CharacterListItem | null>(null);
  const [deleteCharacterTarget, setDeleteCharacterTarget] = useState<CharacterListItem | null>(
    null,
  );
  const [assistantState, setAssistantState] = useState<AssistantSidebarState>({
    agentStatus: "idle",
    isAgentRunning: false,
  });
  const [selectedCharacterLoadVersion, setSelectedCharacterLoadVersion] = useState(0);
  const panelLayout = usePersistedPanelLayout(PANEL_LAYOUT_KEY, PANEL_IDS, !isMobile);
  const isCreatingCharacterRef = useRef(false);
  const skipCharacterRestoreProjectIdRef = useRef<string | null>(null);

  const { data: projectsData } = useQuery({
    queryKey: ["projects", "characters-page"],
    queryFn: () => fetchProjects({ page: 1, pageSize: 100 }),
  });

  const projects = useMemo(() => projectsData?.items ?? [], [projectsData?.items]);

  useEffect(() => {
    const initProject = async () => {
      if (projects.length === 0) return;
      const projectIdFromUrl = projectIdFromRoute ?? searchParams.get("projectId");
      const routeProjectId =
        projectIdFromRoute && projects.some((project) => project.id === projectIdFromRoute)
          ? projectIdFromRoute
          : null;
      if (routeProjectId) {
        if (currentProjectId !== routeProjectId) setCurrentProject(routeProjectId);
        return;
      }
      if (currentProjectId) return;
      const cachedProjectId = await getPreference(LAST_PROJECT_KEY);
      const nextProjectId =
        (projectIdFromUrl && projects.some((project) => project.id === projectIdFromUrl)
          ? projectIdFromUrl
          : null) ??
        (cachedProjectId && projects.some((project) => project.id === cachedProjectId)
          ? cachedProjectId
          : null) ??
        projects[0]?.id ??
        null;
      setCurrentProject(nextProjectId);
    };

    void initProject();
  }, [currentProjectId, projectIdFromRoute, projects, searchParams, setCurrentProject]);

  useEffect(() => {
    if (currentProjectId) void setPreference(LAST_PROJECT_KEY, currentProjectId);
  }, [currentProjectId]);

  useEffect(() => {
    if (skipCharacterRestoreProjectIdRef.current !== currentProjectId) {
      skipCharacterRestoreProjectIdRef.current = null;
    }
  }, [currentProjectId]);

  const { data: charactersData, isLoading: isCharactersLoading } = useQuery({
    queryKey: projectDataQueryKeys.characters.list(currentProjectId),
    queryFn: () => fetchCharactersByProject(currentProjectId!),
    enabled: !!currentProjectId,
    staleTime: 0,
  });

  const characters = useMemo(() => charactersData?.items ?? [], [charactersData?.items]);

  useEffect(() => {
    const restoreCharacter = async () => {
      if (
        !currentProjectId ||
        currentCharacterId ||
        characters.length === 0 ||
        skipCharacterRestoreProjectIdRef.current === currentProjectId
      )
        return;
      const cachedCharacterId = await getPreference(LAST_CHARACTER_KEY);
      const nextCharacterId =
        (cachedCharacterId && characters.some((character) => character.id === cachedCharacterId)
          ? cachedCharacterId
          : null) ?? characters[0].id;
      setCurrentCharacter(nextCharacterId);
    };

    void restoreCharacter();
  }, [characters, currentCharacterId, currentProjectId, setCurrentCharacter]);

  useEffect(() => {
    if (currentCharacterId) void setPreference(LAST_CHARACTER_KEY, currentCharacterId);
  }, [currentCharacterId]);

  useEffect(() => {
    if (!currentCharacterId || characters.length === 0) return;
    if (!characters.some((character) => character.id === currentCharacterId)) {
      setCurrentCharacter(characters[0]?.id ?? null);
    }
  }, [characters, currentCharacterId, setCurrentCharacter]);

  const { data: selectedCharacter, isLoading: isCharacterLoading } = useQuery({
    queryKey: projectDataQueryKeys.characters.loadedDetail(
      currentCharacterId,
      selectedCharacterLoadVersion,
    ),
    queryFn: () => fetchCharacter(currentCharacterId!),
    enabled: !!currentCharacterId,
    staleTime: 0,
    gcTime: 0,
  });

  const upsertCharacterCache = useCallback(
    (updated: CharacterListItem) => {
      queryClient.setQueryData(
        projectDataQueryKeys.characters.list(updated.projectId),
        (old: CharacterListResponse | undefined) => {
          if (!old) return old;
          const exists = old.items.some((character) => character.id === updated.id);
          const items = exists
            ? old.items.map((character) => (character.id === updated.id ? updated : character))
            : [updated, ...old.items];
          return {
            ...old,
            items: sortCharacters(items),
            total: exists ? old.total : old.total + 1,
          };
        },
      );
    },
    [queryClient],
  );

  const removeCharacterCaches = useCallback(
    async (projectId: string, characterIds: string[]) => {
      const deletedCharacterIds = new Set(characterIds);
      await queryClient.cancelQueries({
        queryKey: projectDataQueryKeys.characters.list(projectId),
        exact: true,
      });
      await Promise.all(
        characterIds.map((characterId) =>
          queryClient.cancelQueries({
            queryKey: projectDataQueryKeys.characters.detail(characterId),
          }),
        ),
      );
      queryClient.setQueryData(
        projectDataQueryKeys.characters.list(projectId),
        (old: CharacterListResponse | undefined) => {
          if (!old) return old;
          const items = old.items.filter((character) => !deletedCharacterIds.has(character.id));
          if (items.length === old.items.length) return old;
          return {
            ...old,
            items,
            total: old.total - (old.items.length - items.length),
          };
        },
      );
      characterIds.forEach((characterId) => {
        queryClient.removeQueries({
          queryKey: projectDataQueryKeys.characters.detail(characterId),
        });
      });
    },
    [queryClient],
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createCharacter(currentProjectId!, {
        name: t("characters.untitledCharacter"),
      }),
    onSuccess: (character) => {
      upsertCharacterCache(toCharacterListItem(character));
      queryClient.setQueryData(
        projectDataQueryKeys.characters.loadedDetail(character.id, selectedCharacterLoadVersion),
        character,
      );
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(currentProjectId),
      });
      setCurrentCharacter(character.id);
      toast.success(t("characters.created"));
    },
    onSettled: () => {
      isCreatingCharacterRef.current = false;
    },
  });

  const handleCreateCharacter = () => {
    if (isCreatingCharacterRef.current) return;
    isCreatingCharacterRef.current = true;
    createMutation.mutate();
  };

  const updateMutation = useMutation({
    mutationFn: ({
      characterId,
      data,
    }: {
      characterId: string;
      data: Parameters<typeof updateCharacter>[1];
    }) => updateCharacter(characterId, data),
    onSuccess: (character) => {
      upsertCharacterCache(toCharacterListItem(character));
      queryClient.setQueryData(
        projectDataQueryKeys.characters.loadedDetail(character.id, selectedCharacterLoadVersion),
        character,
      );
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(character.projectId),
      });
      setProfileCharacter(null);
    },
    onError: (error) => {
      const status = (error as { response?: { status?: number } }).response?.status;
      toast.error(status === 409 ? t("characters.nameExists") : t("characters.updateFailed"));
    },
  });

  const writingVisibilityMutation = useMutation({
    mutationFn: ({
      character,
      isWritingVisible,
    }: {
      character: CharacterListItem;
      isWritingVisible: boolean;
    }) => updateCharacter(character.id, { isWritingVisible }),
    onMutate: ({ character, isWritingVisible }) => {
      upsertCharacterCache({
        ...character,
        isWritingVisible,
        updatedAt: new Date().toISOString(),
      });
    },
    onSuccess: (character) => {
      upsertCharacterCache(toCharacterListItem(character));
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(character.projectId),
      });
      toast.success(
        character.isWritingVisible
          ? t("characters.writingVisibilityOn")
          : t("characters.writingVisibilityOff"),
      );
    },
    onError: (_error, { character }) => {
      upsertCharacterCache(character);
      toast.error(t("characters.writingVisibilityFailed"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (characterId: string) => deleteCharacter(characterId),
    onSuccess: async (_data, characterId) => {
      if (!currentProjectId) return;
      if (useCharactersStore.getState().currentCharacterId === characterId) {
        skipCharacterRestoreProjectIdRef.current = currentProjectId;
        setCurrentCharacter(null);
      }
      await removeCharacterCaches(currentProjectId, [characterId]);
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(currentProjectId),
      });
      setDeleteCharacterTarget(null);
      toast.success(t("characters.deleted"));
    },
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (characterIds: string[]) => batchDeleteCharacters(currentProjectId!, characterIds),
    onSuccess: async (_deletedCount, characterIds) => {
      if (!currentProjectId) return;
      const currentCharacterId = useCharactersStore.getState().currentCharacterId;
      if (currentCharacterId && characterIds.includes(currentCharacterId)) {
        skipCharacterRestoreProjectIdRef.current = currentProjectId;
        setCurrentCharacter(null);
      }
      await removeCharacterCaches(currentProjectId, characterIds);
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(currentProjectId),
      });
      toast.success(t("characters.deleted"));
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: string[]) => reorderCharacters(currentProjectId!, orderedIds),
    onMutate: async (orderedIds) => {
      if (!currentProjectId) return {};
      await queryClient.cancelQueries({
        queryKey: projectDataQueryKeys.characters.list(currentProjectId),
        exact: true,
      });
      const previous = queryClient.getQueryData<CharacterListResponse>(
        projectDataQueryKeys.characters.list(currentProjectId),
      );
      const orderById = new Map(orderedIds.map((id, index) => [id, index]));
      queryClient.setQueryData<CharacterListResponse>(
        projectDataQueryKeys.characters.list(currentProjectId),
        (old) =>
          old
            ? {
                ...old,
                items: sortCharacters(
                  old.items.map((character) => ({
                    ...character,
                    order: orderById.get(character.id) ?? character.order,
                  })),
                ),
              }
            : old,
      );
      return { previous };
    },
    onError: (_error, _orderedIds, context) => {
      if (currentProjectId && context?.previous) {
        queryClient.setQueryData(
          projectDataQueryKeys.characters.list(currentProjectId),
          context.previous,
        );
      }
      toast.error(t("writing.orderSaveFailed"));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: projectDataQueryKeys.characters.list(currentProjectId),
      });
      toast.success(t("writing.orderSaved"));
    },
  });

  const handleSelectCharacter = (characterId: string) => {
    queryClient.removeQueries({
      queryKey: projectDataQueryKeys.characters.detail(characterId),
    });
    setCurrentCharacter(characterId);
    setSelectedCharacterLoadVersion((prev) => prev + 1);
    setListOpen(false);
  };

  const list = (
    <CharacterList
      characters={characters}
      projectId={currentProjectId ?? ""}
      selectedCharacterId={currentCharacterId}
      isLoading={isCharactersLoading}
      isCreating={createMutation.isPending}
      onCreateCharacter={handleCreateCharacter}
      onSelectCharacter={handleSelectCharacter}
      onEditProfile={setProfileCharacter}
      onDeleteCharacter={setDeleteCharacterTarget}
      onToggleWritingVisibility={(character, isWritingVisible) => {
        writingVisibilityMutation.mutate({ character, isWritingVisible });
      }}
      onBatchDelete={(characterIds) => batchDeleteMutation.mutate(characterIds)}
      onReorderCharacters={(orderedIds) => reorderMutation.mutate(orderedIds)}
    />
  );

  const editorContent = (
    <CharacterEditor
      key={selectedCharacter?.id ?? "empty"}
      character={selectedCharacter ?? null}
      isSaving={updateMutation.isPending}
      isLoading={shouldShowCharacterEditorLoading(Boolean(selectedCharacter), isCharacterLoading)}
      isAgentLocked={Boolean(currentProjectId && assistantState.isAgentRunning)}
      onSave={async (data) => {
        if (!selectedCharacter) return;
        await updateMutation.mutateAsync({ characterId: selectedCharacter.id, data });
      }}
    />
  );

  return (
    <Flex
      className="characters-page"
      direction="column"
    >
      {currentProjectId && !isMobile && panelLayout.isLoaded ? (
        <Group
          orientation="horizontal"
          className="characters-page-body"
          defaultLayout={panelLayout.defaultLayout}
          onLayoutChanged={panelLayout.onLayoutChanged}
        >
          <Panel
            id="characters-list"
            defaultSize={300}
            minSize={250}
            maxSize={400}
            collapsible={false}
          >
            <Box className="characters-panel characters-page-list-panel">{list}</Box>
          </Panel>

          <Separator className="resize-handle characters-page-separator" />

          <Panel
            id="characters-editor"
            minSize={30}
          >
            <Box className="characters-panel characters-editor-shell">{editorContent}</Box>
          </Panel>

          <Separator className="resize-handle characters-page-separator" />

          <Panel
            id="characters-right"
            defaultSize={500}
            minSize={300}
            maxSize={600}
            collapsible={false}
          >
            <Box className="characters-panel">
              {selectedCharacter ? (
                <AssistantSidebarHost
                  projectId={currentProjectId}
                  preferredAgentKey="discuss"
                  initialComposerMarkup={buildCharacterMentionTag({
                    characterId: selectedCharacter.id,
                    label: selectedCharacter.name,
                  })}
                  replaceComposerWithInitialMarkup
                  onStateChange={setAssistantState}
                  isMobileOverlay={false}
                />
              ) : (
                <Flex
                  height="100%"
                  align="center"
                  justify="center"
                  p="4"
                >
                  <Text color="gray">{t("characters.selectCharacterToDiscuss")}</Text>
                </Flex>
              )}
            </Box>
          </Panel>
        </Group>
      ) : currentProjectId && isMobile ? (
        <Box className="characters-page-body characters-page-body--mobile">
          <Box className="characters-panel characters-editor-shell characters-editor-shell--mobile">
            <Flex
              align="center"
              justify="between"
              px="3"
              py="2"
              className="characters-page-mobile-topbar"
            >
              <Flex
                align="center"
                gap="1"
              >
                <MobileAppSidebarTrigger />
                <Tooltip content={t("characters.listTitle")}>
                  <IconButton
                    variant="ghost"
                    size="2"
                    aria-label={t("characters.listTitle")}
                    onClick={() => setListOpen(!isListOpen)}
                  >
                    <List size={18} />
                  </IconButton>
                </Tooltip>
              </Flex>

              <Tooltip content={t("assistant.mobileTitle")}>
                <IconButton
                  variant="ghost"
                  size="2"
                  aria-label={t("assistant.mobileTitle")}
                  onClick={openAssistantSidebar}
                  disabled={!selectedCharacter}
                >
                  <Bot size={18} />
                </IconButton>
              </Tooltip>
            </Flex>

            <Box className="characters-page-content-fill">{editorContent}</Box>

            <motion.div
              initial={false}
              animate={{ opacity: isListOpen ? 1 : 0 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              onClick={() => setListOpen(false)}
              className="characters-page-mobile-sidebar-backdrop"
              style={{ pointerEvents: isListOpen ? "auto" : "none" }}
            />

            <MotionBox
              initial={false}
              animate={{ x: isListOpen ? 0 : -MOBILE_SIDEBAR_WIDTH }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              className="characters-page-mobile-sidebar-sheet"
              style={{
                width: MOBILE_SIDEBAR_WIDTH,
                minWidth: MOBILE_SIDEBAR_WIDTH,
                pointerEvents: isListOpen ? "auto" : "none",
              }}
            >
              {list}
            </MotionBox>
          </Box>
        </Box>
      ) : currentProjectId ? (
        <PanelLayoutLoading />
      ) : (
        <Flex
          className="characters-project-empty"
          align="center"
          justify="center"
          direction="column"
          gap="2"
        >
          <Text
            size="3"
            weight="medium"
          >
            {t("characters.noProject")}
          </Text>
          <Text
            size="2"
            color="gray"
          >
            {t("characters.noProjectHint")}
          </Text>
        </Flex>
      )}

      {isMobile && currentProjectId && selectedCharacter && (
        <AssistantSidebarHost
          projectId={currentProjectId}
          preferredAgentKey="discuss"
          initialComposerMarkup={buildCharacterMentionTag({
            characterId: selectedCharacter.id,
            label: selectedCharacter.name,
          })}
          replaceComposerWithInitialMarkup
          onStateChange={setAssistantState}
          isMobileOverlay
        />
      )}

      <CharacterProfileDialog
        character={profileCharacter}
        open={!!profileCharacter}
        isSaving={updateMutation.isPending}
        onOpenChange={(open) => {
          if (!open) setProfileCharacter(null);
        }}
        onSubmit={(data) => {
          if (!profileCharacter) return;
          updateMutation.mutate({ characterId: profileCharacter.id, data });
        }}
      />

      <AlertDialog.Root
        open={!!deleteCharacterTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteCharacterTarget(null);
        }}
      >
        <AlertDialog.Content maxWidth="420px">
          <AlertDialog.Title>{t("characters.deleteCharacter")}</AlertDialog.Title>
          <AlertDialog.Description>
            {t("characters.deleteConfirm", { name: deleteCharacterTarget?.name ?? "" })}
          </AlertDialog.Description>
          <Flex
            justify="end"
            gap="3"
            mt="5"
          >
            <AlertDialog.Cancel>
              <Button
                variant="soft"
                color="gray"
              >
                {t("common.cancel")}
              </Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action>
              <Button
                color="red"
                disabled={deleteMutation.isPending}
                onClick={() => {
                  if (deleteCharacterTarget) deleteMutation.mutate(deleteCharacterTarget.id);
                }}
              >
                {t("common.delete")}
              </Button>
            </AlertDialog.Action>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </Flex>
  );
}
