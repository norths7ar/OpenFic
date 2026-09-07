import { useTranslation } from "react-i18next";
import { PhotoProvider, PhotoView } from "react-photo-view";

import "react-photo-view/dist/react-photo-view.css";

import type { AgentMessage } from "@/lib/agent.types";

import { InlineMentionText } from "../../../inline-mention-text";
import { MessageCardShell, UserMessageShell } from "../../shared/message-shell";
import { joinClassNames } from "../../shared/message-shell-utils";

interface UserRequestMessageProps {
  message: AgentMessage;
  onOpenMentionChapter?: (chapterId: string, chapterTitle: string) => void;
}

export function UserRequestMessage({ message, onOpenMentionChapter }: UserRequestMessageProps) {
  const { t } = useTranslation();

  return (
    <UserMessageShell>
      <MessageCardShell className={joinClassNames("ai-sidebar-user-message", "agent-user-message")}>
        <span className="agent-user-message-author">{t("assistant.userMessageLabel")}</span>
        {message.attachments?.length ? (
          <PhotoProvider>
            <div className="agent-user-message-images">
              {message.attachments.map((attachment) => (
                <PhotoView
                  key={attachment.id}
                  src={attachment.url}
                >
                  <button
                    type="button"
                    className="agent-image-preview-trigger"
                    aria-label={t("writing.aiSidebar.viewImage", {
                      fileName: attachment.fileName,
                    })}
                    onClick={(event) => event.stopPropagation()}
                  >
                    <img
                      src={attachment.url}
                      alt={attachment.fileName || t("writing.aiSidebar.userUploadedImage")}
                    />
                  </button>
                </PhotoView>
              ))}
            </div>
          </PhotoProvider>
        ) : null}
        <InlineMentionText
          text={message.content ?? ""}
          className="agent-user-message-text"
          onOpenMentionChapter={onOpenMentionChapter}
        />
      </MessageCardShell>
    </UserMessageShell>
  );
}
