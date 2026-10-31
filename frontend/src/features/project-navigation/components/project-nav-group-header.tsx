import "./project-nav-group-header.css";
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
      className="project-nav-group-header__rename-input"
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
      className="project-nav-group-header project-nav-group-header__surface"
      initial={false}
      onContextMenu={onContextMenu}
      transition={VOLUME_HEADER_TRANSITION}
    >
      <motion.div
        initial={false}
        aria-hidden="true"
        animate={{ opacity: isExpanded ? 1 : 0 }}
        transition={VOLUME_HEADER_TRANSITION}
        className="project-nav-group-header__hover-overlay"
      />
      <motion.div
        initial={false}
        aria-hidden="true"
        animate={{
          opacity: isExpanded ? 1 : 0,
          scaleX: isExpanded ? 1 : 0.96,
        }}
        transition={VOLUME_HEADER_TRANSITION}
        className="project-nav-group-header__progress"
      />
      <Flex
        align="center"
        gap="2"
        px="3"
        py="2"
        className="project-nav-group-header__row"
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
            className="project-nav-group-header__chevron"
          >
            <ChevronRight size={15} />
          </motion.div>
        </IconButton>

        <Box
          className="project-nav-group-header__title-slot"
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
              className="project-nav-group-header__editable-title"
            >
              {title}
            </Text>
          )}
          {description ? (
            <Text
              size="1"
              color="gray"
              className="project-nav-group-header__title"
            >
              {description}
            </Text>
          ) : null}
        </Box>

        <Text
          size="1"
          color="gray"
          className="project-nav-group-header__count"
        >
          {count}
        </Text>

        {actions}
      </Flex>
    </MotionBox>
  );
}
