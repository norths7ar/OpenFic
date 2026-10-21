from langchain_core.messages import HumanMessage

from app.agent_runtime.context.processors.to_langchain import to_langchain_messages
from app.agent_runtime.context.types import ContextMessage


def test_user_message_with_image_attachments_mapped_to_multimodal_content() -> None:
    parts = [
        ContextMessage(
            role="user",
            content="描述这张图",
            attachments=[
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "base64": "aW1hZ2U=",
                }
            ],
        )
    ]

    out = to_langchain_messages(parts)

    assert isinstance(out[0], HumanMessage)
    assert out[0].content == [
        {"type": "text", "text": "描述这张图"},
        {"type": "image", "base64": "aW1hZ2U=", "mime_type": "image/png"},
    ]
