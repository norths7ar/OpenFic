import { Button, Dialog, Flex, SegmentedControl, Text, TextArea } from "@radix-ui/themes";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { buildChapterMentionTag } from "@/features/assistant/lib/mention-text";
import type {
  SceneDraftContextMode,
  SceneDraftRequest,
} from "@/features/assistant/lib/scene-draft";

interface SceneDraftDialogProps {
  chapterId: string;
  chapterTitle: string;
  baseUpdatedAt: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPrepare: (request: SceneDraftRequest) => void;
}

export function SceneDraftDialog({
  chapterId,
  chapterTitle,
  baseUpdatedAt,
  open,
  onOpenChange,
  onPrepare,
}: SceneDraftDialogProps) {
  const { t } = useTranslation();
  const [contextMode, setContextMode] = useState<SceneDraftContextMode>("local");
  const [goal, setGoal] = useState("");

  useEffect(() => {
    if (!open) return;
    setContextMode("local");
    setGoal("");
  }, [open]);

  const handlePrepare = () => {
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) return;
    const chapterLabel = chapterTitle.trim() || t("writing.untitledChapter");
    const chapterMention = buildChapterMentionTag({ chapterId, label: chapterLabel });
    onPrepare({
      chapterId,
      chapterTitle: chapterLabel,
      baseUpdatedAt,
      contextMode,
      prompt: [
        t("writing.sceneDraft.promptLead"),
        chapterMention,
        `${t("writing.sceneDraft.promptGoal")}：${trimmedGoal}`,
        t("writing.sceneDraft.promptOutput"),
      ].join("\n\n"),
    });
    onOpenChange(false);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={onOpenChange}
    >
      <Dialog.Content maxWidth="560px">
        <Dialog.Title>{t("writing.sceneDraft.title")}</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
        >
          {t("writing.sceneDraft.description", { chapter: chapterTitle })}
        </Dialog.Description>

        <Flex
          direction="column"
          gap="4"
          mt="4"
        >
          <Flex
            direction="column"
            gap="2"
          >
            <Text
              size="2"
              weight="medium"
            >
              {t("writing.sceneDraft.scopeLabel")}
            </Text>
            <SegmentedControl.Root
              value={contextMode}
              onValueChange={(value) => setContextMode(value as SceneDraftContextMode)}
            >
              <SegmentedControl.Item value="local">
                {t("writing.sceneDraft.scopeLocal")}
              </SegmentedControl.Item>
              <SegmentedControl.Item value="global">
                {t("writing.sceneDraft.scopeGlobal")}
              </SegmentedControl.Item>
            </SegmentedControl.Root>
            <Text
              size="1"
              color="gray"
            >
              {contextMode === "local"
                ? t("writing.sceneDraft.scopeLocalHint")
                : t("writing.sceneDraft.scopeGlobalHint")}
            </Text>
          </Flex>

          <Flex
            direction="column"
            gap="2"
          >
            <Text
              size="2"
              weight="medium"
            >
              {t("writing.sceneDraft.goalLabel")}
            </Text>
            <TextArea
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder={t("writing.sceneDraft.goalPlaceholder")}
              rows={6}
              autoFocus
            />
            <Text
              size="1"
              color="gray"
            >
              {t("writing.sceneDraft.mentionHint")}
            </Text>
          </Flex>
        </Flex>

        <Flex
          gap="3"
          mt="5"
          justify="end"
        >
          <Dialog.Close>
            <Button
              variant="soft"
              color="gray"
            >
              {t("common.cancel")}
            </Button>
          </Dialog.Close>
          <Button
            onClick={handlePrepare}
            disabled={!goal.trim()}
          >
            {t("writing.sceneDraft.prepare")}
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
