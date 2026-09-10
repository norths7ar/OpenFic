import { Badge, Text } from "@radix-ui/themes";
import { ArrowUpRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import type { AgentMessage } from "@/lib/agent.types";

import { ToolBody } from "../shared/tool-message-shared";
import { asString, getToolErrorMessage } from "../shared/tool-message-utils";
import { getProjectChangeSummary } from "./project-change-summary";

import "./project-change-tool-message.css";

export function ProjectChangeToolMessage({ message }: { message: AgentMessage }) {
  const { t } = useTranslation();
  const { projectId } = useParams();
  const error = getToolErrorMessage(message);
  const { change, title, material, operation, fields } = getProjectChangeSummary(message);
  const changeId = asString(change?.id);
  const failed = message.status === "error" || message.toolSuccess === false;
  const interrupted = ["cancelled", "interrupted"].includes(
    asString(message.toolResult?.reason) ?? "",
  );
  const submitted = Boolean(changeId) && !failed;
  const finishedWithoutResult = message.status === "completed" && !submitted;
  const status = interrupted
    ? "notSubmitted"
    : failed
      ? "failed"
      : submitted
        ? "submitted"
        : finishedWithoutResult
          ? "notSubmitted"
          : "generating";
  const heading = t(
    title
      ? "pendingProjectChanges.changeHeading"
      : "pendingProjectChanges.changeHeadingWithoutTitle",
    {
      operation: t(`pendingProjectChanges.operations.${operation}`),
      material: t(`pendingProjectChanges.materialTypes.${material}`),
      title,
    },
  );
  return (
    <ToolBody>
      <div className="project-change-card">
        <div className="project-change-card-heading">
          <Text
            size="2"
            weight="medium"
          >
            {heading}
          </Text>
          <Badge
            color={failed ? "red" : submitted ? "amber" : "gray"}
            variant="soft"
          >
            {t(`assistant.tools.proposalStatus.${status}`)}
          </Badge>
        </div>
        {error ? (
          <Text
            size="2"
            color="red"
            className="project-change-card-error"
          >
            {error}
          </Text>
        ) : null}
        {submitted && operation === "update" && fields.length > 0 ? (
          <Text
            size="1"
            color="gray"
          >
            {t("pendingProjectChanges.changedFields")}：
            {fields.map((field) => t(`assistant.tools.proposalFields.${field}`)).join("、")}
          </Text>
        ) : null}
        {submitted && projectId && changeId ? (
          <Link
            className="project-change-card-link"
            to={`/projects/${encodeURIComponent(projectId)}/changes?change=${encodeURIComponent(changeId)}`}
          >
            {t("assistant.tools.viewProjectChange")}
            <ArrowUpRight
              size={14}
              aria-hidden="true"
            />
          </Link>
        ) : null}
      </div>
    </ToolBody>
  );
}
