"""
Import API 测试。
"""


import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_preview_gb18030_preserves_original_text(client: AsyncClient) -> None:
    """测试 GB18030 编码文件预览时不会出现乱码。"""
    content = "第一章 扩展字符测试\n\n这里有扩展字：𠮷。"
    gb18030_content = content.encode("gb18030")
    files = {"file": ("gb18030_novel.txt", gb18030_content, "text/plain")}

    response = await client.post("/api/v1/import/preview", files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["detected_encoding"].lower() == "gb18030"
    assert data["volumes"][0]["chapters"][0]["title"] == "第一章 扩展字符测试"
    assert data["volumes"][0]["chapters"][0]["content_preview"] == "这里有扩展字：𠮷。"
