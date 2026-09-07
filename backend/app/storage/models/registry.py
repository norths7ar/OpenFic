"""Import every SQLModel table for migration metadata registration."""

from app.agent_runtime.persistence.model import (
    AgentAttachment,
    AgentContextCompaction,
    AgentRunMessage,
)
from app.background.jobs.models import BackgroundJob, BackgroundJobEvent, BackgroundJobItem
from app.models.entities.model import Model
from app.models.entities.model_provider import ModelProvider
from app.storage.models.agent_memory import AgentMemory
from app.storage.models.agent_rule import AgentRule
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.character import Character
from app.storage.models.commit import Commit
from app.storage.models.llm_audit_log import LLMAuditLog
from app.storage.models.note import Note
from app.storage.models.pending_project_change import PendingProjectChange
from app.storage.models.project import Project
from app.storage.models.project_folder import ProjectFolder
from app.storage.models.project_import_binding import ProjectImportBinding
from app.storage.models.project_import_profile import ProjectImportProfile
from app.storage.models.prompt_chain_version import PromptChainVersion
from app.storage.models.prompt_entry import PromptEntry
from app.storage.models.retrieval_chapter_index_state import RetrievalChapterIndexState
from app.storage.models.retrieval_index import RetrievalIndex
from app.storage.models.revision import Revision
from app.storage.models.revision_chapter_snapshot import RevisionChapterSnapshot
from app.storage.models.revision_character_snapshot import RevisionCharacterSnapshot
from app.storage.models.revision_content_blob import RevisionContentBlob
from app.storage.models.revision_note_snapshot import (
    RevisionNoteCategorySnapshot,
    RevisionNoteSnapshot,
)
from app.storage.models.revision_world_entry_snapshot import RevisionWorldEntrySnapshot
from app.storage.models.setting import Setting
from app.storage.models.skill import Skill
from app.storage.models.skill_reference_doc import SkillReferenceDoc
from app.storage.models.task import Task
from app.storage.models.task_message import TaskMessage
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.models.writing_activity_event import WritingActivityEvent

__all__ = [
    "AgentAttachment",
    "AgentContextCompaction",
    "AgentMemory",
    "AgentRule",
    "AgentRunMessage",
    "BackgroundJob",
    "BackgroundJobEvent",
    "BackgroundJobItem",
    "Character",
    "Chapter",
    "ChapterSummary",
    "Commit",
    "LLMAuditLog",
    "Model",
    "ModelProvider",
    "Note",
    "ProjectFolder",
    "PendingProjectChange",
    "Project",
    "ProjectImportBinding",
    "ProjectImportProfile",
    "PromptChainVersion",
    "PromptEntry",
    "RetrievalChapterIndexState",
    "RetrievalIndex",
    "Revision",
    "RevisionChapterSnapshot",
    "RevisionCharacterSnapshot",
    "RevisionContentBlob",
    "RevisionNoteCategorySnapshot",
    "RevisionNoteSnapshot",
    "RevisionWorldEntrySnapshot",
    "Setting",
    "Skill",
    "SkillReferenceDoc",
    "Task",
    "TaskMessage",
    "WorldInfo",
    "WorldInfoEntry",
    "WritingActivityEvent",
]
