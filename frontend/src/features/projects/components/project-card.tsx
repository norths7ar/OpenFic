import "./project-card.css";
/**
 * ProjectCard Component
 *
 * Grid 视图下的项目卡片组件。
 */
import { Box, Card, Flex, Text, IconButton, Tooltip } from "@radix-ui/themes";
import { BookOpen, Database, Edit2, Trash2 } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import type { Project } from "@/lib/project.types";
import { formatRelativeTime } from "@/lib/time-utils";

const MotionCard = motion.create(Card);

interface ProjectCardProps {
  project: Project;
  onEdit: (project: Project) => void;
  onManageData: (project: Project) => void;
  onDelete: (project: Project) => void;
}

export function ProjectCard({ project, onEdit, onManageData, onDelete }: ProjectCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/projects/${project.id}/write`);
  };

  return (
    <MotionCard
      size="2"
      variant="ghost"
      className="project-card__surface"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -4, backgroundColor: "var(--gray-a3)" }}
      transition={{ duration: 0.2 }}
      onClick={handleClick}
    >
      {/* 封面图 */}
      <Box
        className="project-card__cover"
        style={{ background: project.coverUrl ? "transparent" : "var(--gray-a3)" }}
      >
        {project.coverUrl ? (
          <img
            src={project.coverUrl}
            alt={project.title}
            className="project-card__cover-image"
          />
        ) : (
          <Flex
            align="center"
            justify="center"
            className="project-card__cover-placeholder"
          >
            <BookOpen
              size={48}
              className="project-card__cover-icon"
            />
          </Flex>
        )}
      </Box>

      {/* 项目信息 */}
      <Box>
        <Text
          size="3"
          weight="bold"
          className="project-card__title"
          truncate
        >
          {project.title}
        </Text>

        <Flex
          gap="2"
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
            ·
          </Text>
          <Text
            size="1"
            color="gray"
          >
            {project.chapterCount} {t("projects.chapters")}
          </Text>
        </Flex>

        <Flex
          justify="between"
          align="center"
          mt="1"
        >
          <Text
            size="1"
            color="gray"
          >
            {formatRelativeTime(project.updatedAt)}
          </Text>
          <Flex
            gap="3"
            ml="2"
          >
            <Tooltip content={t("projectData.open")}>
              <IconButton
                size="1"
                variant="ghost"
                aria-label={t("projectData.open")}
                onClick={(e) => {
                  e.stopPropagation();
                  onManageData(project);
                }}
              >
                <Database size={14} />
              </IconButton>
            </Tooltip>
            <Tooltip content={t("common.edit")}>
              <IconButton
                size="1"
                variant="ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(project);
                }}
              >
                <Edit2 size={14} />
              </IconButton>
            </Tooltip>
            <Tooltip content={t("common.delete")}>
              <IconButton
                size="1"
                variant="ghost"
                color="red"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(project);
                }}
              >
                <Trash2 size={14} />
              </IconButton>
            </Tooltip>
          </Flex>
        </Flex>
      </Box>
    </MotionCard>
  );
}
