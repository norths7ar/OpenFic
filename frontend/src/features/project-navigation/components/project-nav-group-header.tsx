import { Box, Flex, IconButton, Text } from "@radix-ui/themes";
import { ChevronRight } from "lucide-react";
import { motion } from "motion/react";
import { useCallback, useState, type MouseEventHandler, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

const MotionBox = motion.create(Box);
const VOLUME_HEADER_TRANSITION = { duration: 0.2, ease: [0.22, 1, 0.36, 1] } as const;

function HeaderRenameInput({
  initialValue,
  onConfirm,
  onCancel,
}: {
  initialValue: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);

  const submit = useCallback(() => {
    const nextValue = value.trim();
    if (nextValue && nextValue !== initialValue) {
      onConfirm(nextValue);
      return;
    }
    onCancel();
  }, [initialValue, onCancel, onConfirm, value]);

  return (
    <input
      autoFocus
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onBlur={submit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          submit();
        }
        if (event.key === "Escape") {
          event.preventDefault();
          onCancel();
        }
      }}
      onClick={(event) => event.stopPropagation()}
      style={{
        width: "100%",
        height: 22,
        border: "none",
        outline: "none",
        background: "transparent",
        color: "var(--gray-12)",
        fontFamily: "inherit",
        fontSize: "var(--font-size-base)",
        fontWeight: 600,
      }}
    />
  );
}

export interface ProjectNavGroupHeaderProps {
  title: string;
  description?: string | null;
  count?: ReactNode;
  actions?: ReactNode;
  isExpanded: boolean;
  isRenaming?: boolean;
  onToggle: () => void;
  onRenameConfirm?: (title: string) => void;
  onRenameCancel?: () => void;
  onContextMenu?: MouseEventHandler<HTMLDivElement>;
}

export function ProjectNavGroupHeader({
  title,
  description,
  count,
  actions,
  isExpanded,
  isRenaming = false,
  onToggle,
  onRenameConfirm,
  onRenameCancel,
  onContextMenu,
}: ProjectNavGroupHeaderProps) {
  const { t } = useTranslation();
  return (
    <MotionBox
      className="project-nav-group-header"
      initial={false}
      onContextMenu={onContextMenu}
      transition={VOLUME_HEADER_TRANSITION}
      style={{
        borderTop: "1px solid var(--gray-a4)",
        background: "var(--gray-2)",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <motion.div
        initial={false}
        aria-hidden="true"
        animate={{ opacity: isExpanded ? 1 : 0 }}
        transition={VOLUME_HEADER_TRANSITION}
        style={{
          position: "absolute",
          inset: 0,
          background: "var(--gray-a2)",
          pointerEvents: "none",
        }}
      />
      <motion.div
        initial={false}
        aria-hidden="true"
        animate={{
          opacity: isExpanded ? 1 : 0,
          scaleX: isExpanded ? 1 : 0.96,
        }}
        transition={VOLUME_HEADER_TRANSITION}
        style={{
          position: "absolute",
          right: 0,
          bottom: 0,
          left: 0,
          height: 1,
          background: "var(--gray-a3)",
          transformOrigin: "left center",
          pointerEvents: "none",
        }}
      />
      <Flex
        align="center"
        gap="2"
        px="3"
        py="2"
        style={{ minWidth: 0 }}
      >
        <IconButton
          variant="ghost"
          color="gray"
          size="1"
          onClick={onToggle}
          aria-label={isExpanded ? t("projectNavigation.collapse") : t("projectNavigation.expand")}
        >
          <motion.div
            initial={false}
            animate={{ rotate: isExpanded ? 90 : 0 }}
            transition={VOLUME_HEADER_TRANSITION}
            style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <ChevronRight size={15} />
          </motion.div>
        </IconButton>

        <Box
          style={{ flex: 1, minWidth: 0 }}
          onClick={onToggle}
        >
          {isRenaming && onRenameConfirm && onRenameCancel ? (
            <HeaderRenameInput
              initialValue={title}
              onConfirm={onRenameConfirm}
              onCancel={onRenameCancel}
            />
          ) : (
            <Text
              size="2"
              weight="bold"
              style={{
                display: "block",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                color: "var(--gray-12)",
                cursor: "pointer",
              }}
            >
              {title}
            </Text>
          )}
          {description ? (
            <Text
              size="1"
              color="gray"
              style={{
                display: "block",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {description}
            </Text>
          ) : null}
        </Box>

        <Text
          size="1"
          color="gray"
          style={{ flexShrink: 0 }}
        >
          {count}
        </Text>

        {actions}
      </Flex>
    </MotionBox>
  );
}
