import { Box, Button, Card, Flex, Text } from "@radix-ui/themes";
import { Download, RotateCw, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  BrowserBackupError,
  createBrowserBackup,
  downloadBrowserBackup,
  isBrowserBackupTargetEmpty,
  parseBrowserBackupJson,
  restoreBrowserBackup,
} from "@/lib/browser-backup";

function message(error: unknown, fallback: string): string {
  return error instanceof BrowserBackupError ? error.message : fallback;
}

export function BrowserBackupSettings() {
  const { i18n } = useTranslation();
  const isChinese = i18n.language.startsWith("zh");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);

  const copy = isChinese
    ? {
        title: "浏览器伴随包",
        description:
          "导出本浏览器档案中的未提交草稿、编辑状态和 OpenFic 偏好；它需与服务端完整快照一同保存。",
        scope: "只包含本浏览器中的 OpenFic 数据，不包含服务端正文、附件或其他浏览器档案。",
        export: "导出浏览器伴随包",
        import: "导入浏览器伴随包",
        importHint:
          "仅能导入到没有项目、编辑状态或草稿的新浏览器档案；新档案生成的语言和界面偏好会替换为备份中的偏好。",
        exporting: "正在导出…",
        importing: "正在导入…",
        exportFailed: "无法导出浏览器伴随包。",
        importFailed: "无法导入浏览器伴随包。",
        invalidFile: "请选择 OpenFic 浏览器伴随包 JSON 文件。",
        restored: "已导入。重新加载页面后，草稿和偏好将恢复为备份中的状态。",
        reload: "立即重新加载",
      }
    : {
        title: "Browser companion package",
        description:
          "Export uncommitted drafts, editor state, and OpenFic preferences from this browser profile. Keep it with the full server snapshot.",
        scope:
          "It contains OpenFic data from this browser only, not server content, attachments, or other browser profiles.",
        export: "Export browser package",
        import: "Import browser package",
        importHint:
          "Import works only in a new browser profile with no projects, editor state, or drafts. Its default language and interface preferences are replaced by the backup.",
        exporting: "Exporting…",
        importing: "Importing…",
        exportFailed: "Could not export the browser package.",
        importFailed: "Could not import the browser package.",
        invalidFile: "Choose an OpenFic browser package JSON file.",
        restored: "Imported. Reload the page to restore the saved drafts and preferences.",
        reload: "Reload now",
      };

  const handleExport = async () => {
    setIsWorking(true);
    setError(null);
    try {
      downloadBrowserBackup(await createBrowserBackup());
    } catch (exportError) {
      setError(message(exportError, copy.exportFailed));
    } finally {
      setIsWorking(false);
    }
  };

  const handleImport = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".json")) {
      setError(copy.invalidFile);
      return;
    }
    setIsWorking(true);
    setError(null);
    try {
      const backup = parseBrowserBackupJson(await file.text());
      if (!(await isBrowserBackupTargetEmpty())) {
        throw new BrowserBackupError(
          isChinese
            ? "仅能导入到没有项目、编辑状态或草稿的新浏览器档案；现有内容不会被覆盖。"
            : "Import only works in a new browser profile with no projects, editor state, or drafts; existing content will not be overwritten.",
        );
      }
      await restoreBrowserBackup(backup);
      setRestored(true);
    } catch (importError) {
      setError(message(importError, copy.importFailed));
    } finally {
      setIsWorking(false);
    }
  };

  return (
    <Card variant="surface">
      <Flex
        direction="column"
        gap="3"
      >
        <Box>
          <Text
            as="p"
            size="2"
            weight="medium"
          >
            {copy.title}
          </Text>
          <Text
            as="p"
            size="1"
            color="gray"
            mt="1"
          >
            {copy.description}
          </Text>
          <Text
            as="p"
            size="1"
            color="gray"
            mt="1"
          >
            {copy.scope}
          </Text>
        </Box>

        <Flex
          align="center"
          gap="2"
          wrap="wrap"
        >
          <Button
            variant="soft"
            onClick={() => void handleExport()}
            disabled={isWorking || restored}
          >
            <Download size={16} />
            {isWorking ? copy.exporting : copy.export}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            hidden
            disabled={isWorking || restored}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void handleImport(file);
            }}
          />
          <Button
            variant="soft"
            color="gray"
            onClick={() => fileInputRef.current?.click()}
            disabled={isWorking || restored}
          >
            <Upload size={16} />
            {isWorking ? copy.importing : copy.import}
          </Button>
        </Flex>

        <Text
          size="1"
          color="gray"
        >
          {copy.importHint}
        </Text>

        {error ? (
          <Text
            size="1"
            color="red"
          >
            {error}
          </Text>
        ) : null}

        {restored ? (
          <Flex
            align="center"
            gap="2"
            wrap="wrap"
          >
            <Text
              size="1"
              color="green"
            >
              {copy.restored}
            </Text>
            <Button
              size="1"
              variant="soft"
              onClick={() => window.location.reload()}
            >
              <RotateCw size={14} />
              {copy.reload}
            </Button>
          </Flex>
        ) : null}
      </Flex>
    </Card>
  );
}
