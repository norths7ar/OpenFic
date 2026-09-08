import { Button, Dialog, Flex, Text } from "@radix-ui/themes";
import { useEffect, useMemo, useState } from "react";

import type { WritingWorkingCopyConflict } from "../lib/writing-working-copy";

interface WritingConflictDialogProps {
  conflict: WritingWorkingCopyConflict;
  onAdoptLocal: () => Promise<void>;
  onUseSaved: () => Promise<void>;
}

export function WritingConflictDialog({
  conflict,
  onAdoptLocal,
  onUseSaved,
}: WritingConflictDialogProps) {
  const [open, setOpen] = useState(true);
  const [isApplying, setIsApplying] = useState(false);
  const conflictKey = useMemo(
    () =>
      [
        conflict.local.title,
        conflict.local.content,
        conflict.local.updatedAt.getTime(),
        conflict.remote.title,
        conflict.remote.content,
        conflict.remote.updatedAt,
      ].join("\u0000"),
    [conflict],
  );

  useEffect(() => {
    setOpen(true);
  }, [conflictKey]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={setOpen}
    >
      <Dialog.Content maxWidth="900px">
        <Dialog.Title>检测到两个版本</Dialog.Title>
        <Dialog.Description
          size="2"
          color="gray"
        >
          已保留本地未保存草稿和已保存版本。关闭此窗口不会覆盖任何内容。
        </Dialog.Description>
        <Flex
          gap="3"
          mt="4"
          style={{ minHeight: 260 }}
        >
          <Flex
            direction="column"
            gap="1"
            style={{ flex: 1, minWidth: 0 }}
          >
            <Text
              size="2"
              weight="medium"
            >
              本地草稿
            </Text>
            <textarea
              readOnly
              value={`${conflict.local.title}\n\n${conflict.local.content}`}
              style={{ flex: 1, resize: "vertical" }}
            />
          </Flex>
          <Flex
            direction="column"
            gap="1"
            style={{ flex: 1, minWidth: 0 }}
          >
            <Text
              size="2"
              weight="medium"
            >
              已保存版本
            </Text>
            <textarea
              readOnly
              value={`${conflict.remote.title}\n\n${conflict.remote.content}`}
              style={{ flex: 1, resize: "vertical" }}
            />
          </Flex>
        </Flex>
        <Flex
          justify="end"
          gap="2"
          mt="4"
        >
          <Button
            variant="soft"
            color="gray"
            onClick={() => setOpen(false)}
          >
            保留本地草稿
          </Button>
          <Button
            variant="soft"
            disabled={isApplying}
            onClick={() => {
              setIsApplying(true);
              void onAdoptLocal()
                .then(() => setOpen(false))
                .catch(() => undefined)
                .finally(() => setIsApplying(false));
            }}
          >
            采用本地版本
          </Button>
          <Button
            color="red"
            disabled={isApplying}
            onClick={() => {
              setIsApplying(true);
              void onUseSaved()
                .then(() => setOpen(false))
                .catch(() => undefined)
                .finally(() => setIsApplying(false));
            }}
          >
            使用已保存版本
          </Button>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
