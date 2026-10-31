import "./project-list-item.css";
/**
 * ProjectListItem Component
 *
 * List 视图下的项目列表项组件。
 */
import { Box, Card, Flex, Text, IconButton, Tooltip } from "@radix-ui/themes";
import { BookOpen, Database, Edit2, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import type { Project } from "@/lib/project.types";
import { formatRelativeTime } from "@/lib/time-utils";

const MotionCard = motion.create(Card);

interface ProjectListItemProps {
  project: Project;
  onEdit: (project: Project) => void;
  onManageData: (project: Project) => void;
  onDelete: (project: Project) => void;
}

export function ProjectListItem({ project, onEdit, onManageData, onDelete }: ProjectListItemProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/projects/${project.id}/write`);
  };

  return (
    <MotionCard
      size="2"
      className="project-list-item__surface"
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      whileHover={{ x: 4 }}
      transition={{ duration: 0.2 }}
      onClick={handleClick}
    >
      <Flex
        align="center"
        gap="4"
      >
        {/* 左侧小封面 */}
        <Box
          className="project-list-item__cover"
          style={{ background: project.coverUrl ? "transparent" : "var(--gray-a3)" }}
        >
          {project.coverUrl ? (
            <img
              src={project.coverUrl}
              alt={project.title}
              className="project-list-item__cover-image"
            />
          ) : (
            <Flex
              align="center"
              justify="center"
              className="project-list-item__cover-placeholder"
            >
              <BookOpen
                size={24}
                className="project-list-item__cover-icon"
              />
            </Flex>
          )}
        </Box>

        {/* 中间项目信息 */}
        <Box className="project-list-item__details">
          <Text
            size="3"
            weight="bold"
            truncate
          >
            {project.title}
          </Text>
          {project.description && (
            <Text
              size="2"
              color="gray"
              truncate
              className="project-list-item__title"
            >
              {project.description}
            </Text>
          )}
          <Flex
            gap="3"
            mt="1"
            align="center"
          >
            <Text
              size="1"
              color="gray"
            >
              {project.wordCount.toLocaleString()} {t("projects.words")}
            </Text>
            <Text
              size="1"
              color="gray"
            >
              {project.chapterCount} {t("projects.chapters")}
            </Text>
            <Text
              size="1"
              color="gray"
            >
              {formatRelativeTime(project.updatedAt)}
            </Text>
          </Flex>
        </Box>

        {/* 右侧操作按钮 */}
        <Flex
          gap="3"
          align="center"
        >
          <Tooltip content={t("projectData.open")}>
            <IconButton
              size="2"
              variant="ghost"
              aria-label={t("projectData.open")}
              onClick={(e) => {
                e.stopPropagation();
                onManageData(project);
              }}
            >
              <Database size={16} />
            </IconButton>
          </Tooltip>
          <Tooltip content={t("common.edit")}>
            <IconButton
              size="2"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                onEdit(project);
              }}
            >
              <Edit2 size={16} />
            </IconButton>
          </Tooltip>
          <Tooltip content={t("common.delete")}>
            <IconButton
              size="2"
              variant="ghost"
              color="red"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(project);
              }}
            >
              <Trash2 size={16} />
            </IconButton>
          </Tooltip>
        </Flex>
      </Flex>
    </MotionCard>
  );
}
