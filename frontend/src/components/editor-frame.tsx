import { Box, Flex, Text } from "@radix-ui/themes";
import type { CSSProperties, HTMLAttributes, ReactNode, Ref } from "react";

import { EditorToolbar, type EditorToolbarProps } from "./editor-toolbar";
import { TitleInput, type TitleInputProps } from "./title-input";

interface EditorFrameProps {
  toolbar: EditorToolbarProps;
  title: TitleInputProps;
  statistics: ReactNode;
  saveStatus: ReactNode;
  children: ReactNode;
  banner?: ReactNode;
  beforeContent?: ReactNode;
  overlays?: ReactNode;
  scrollRef?: Ref<HTMLDivElement>;
  scrollProps?: Omit<HTMLAttributes<HTMLDivElement>, "children" | "style">;
  bodyRef?: Ref<HTMLDivElement>;
  onBodyKeyDownCapture?: HTMLAttributes<HTMLDivElement>["onKeyDownCapture"];
  maxWidth?: number;
  contentStyle?: CSSProperties;
}

/** Shared editor layout; document state and serialization belong to the caller. */
export function EditorFrame({
  toolbar,
  title,
  statistics,
  saveStatus,
  children,
  banner,
  beforeContent,
  overlays,
  scrollRef,
  scrollProps,
  bodyRef,
  onBodyKeyDownCapture,
  maxWidth = 800,
  contentStyle,
}: EditorFrameProps) {
  return (
    <Flex
      data-slot="editor-frame"
      direction="column"
      style={{ height: "100%", minHeight: 0, minWidth: 0, flex: 1 }}
    >
      {banner}
      <EditorToolbar {...toolbar} />
      {beforeContent}
      <Box
        {...scrollProps}
        data-slot="editor-scroll-area"
        ref={scrollRef}
        className={`tiptap-editor-wrapper ${scrollProps?.className ?? ""}`}
        style={{ flex: 1, minHeight: 0, overflow: "auto" }}
      >
        <Box
          className="editor-frame-content"
          style={{ maxWidth, ...contentStyle }}
        >
          <TitleInput {...title} />
          <Box style={{ borderBottom: "1px solid var(--gray-a4)" }} />
          <Box
            py="5"
            ref={bodyRef}
            onKeyDownCapture={onBodyKeyDownCapture}
          >
            {children}
          </Box>
        </Box>
      </Box>
      <Flex
        data-slot="editor-status-bar"
        px="6"
        py="3"
        justify="between"
        align="center"
        style={{
          flexShrink: 0,
          borderTop: "1px solid var(--gray-a4)",
          background: "var(--gray-a2)",
        }}
      >
        <Text
          size="1"
          color="gray"
        >
          {statistics}
        </Text>
        <Text
          size="1"
          color="gray"
        >
          {saveStatus}
        </Text>
      </Flex>
      {overlays}
    </Flex>
  );
}
