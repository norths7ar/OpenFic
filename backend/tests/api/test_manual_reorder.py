import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/projects", data={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_reorder_characters_updates_zero_based_order(client: AsyncClient) -> None:
    project_id = await _project(client, "角色排序")
    first = await client.post(f"/api/v1/projects/{project_id}/characters", data={"name": "甲"})
    second = await client.post(f"/api/v1/projects/{project_id}/characters", data={"name": "乙"})
    ids = [first.json()["id"], second.json()["id"]]

    response = await client.post(
        f"/api/v1/projects/{project_id}/characters/reorder",
        json={"ordered_ids": ids[::-1]},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 2}

    listed = (await client.get(f"/api/v1/projects/{project_id}/characters")).json()["items"]
    assert [(item["id"], item["order"]) for item in listed] == [
        (ids[1], 0),
        (ids[0], 1),
    ]


@pytest.mark.asyncio
async def test_reorder_note_category_and_notes_updates_siblings(
    client: AsyncClient,
) -> None:
    project_id = await _project(client, "笔记排序")
    categories = [
        (
            await client.post(
                f"/api/v1/projects/{project_id}/note-categories", json={"title": title}
            )
        ).json()
        for title in ("甲", "乙")
    ]
    category_ids = [item["id"] for item in categories]
    response = await client.post(
        f"/api/v1/projects/{project_id}/note-items/reorder",
        json={"kind": "category", "parent_id": None, "ordered_ids": category_ids[::-1]},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 2}

    notes = [
        (
            await client.post(
                f"/api/v1/projects/{project_id}/notes",
                json={"title": title, "category_id": category_ids[0]},
            )
        ).json()
        for title in ("一", "二")
    ]
    note_ids = [item["id"] for item in notes]
    response = await client.post(
        f"/api/v1/projects/{project_id}/note-items/reorder",
        json={
            "kind": "note",
            "parent_id": category_ids[0],
            "ordered_ids": note_ids[::-1],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 2}


@pytest.mark.asyncio
async def test_reorder_mixed_note_items_preserves_one_sibling_order(
    client: AsyncClient,
) -> None:
    project_id = await _project(client, "笔记混排")
    first_category = (
        await client.post(
            f"/api/v1/projects/{project_id}/note-categories",
            json={"title": "甲"},
        )
    ).json()
    note = (
        await client.post(
            f"/api/v1/projects/{project_id}/notes",
            json={"title": "中间笔记"},
        )
    ).json()
    second_category = (
        await client.post(
            f"/api/v1/projects/{project_id}/note-categories",
            json={"title": "乙"},
        )
    ).json()

    assert [first_category["order"], note["order"], second_category["order"]] == [
        1,
        2,
        2,
    ]
    ordered_items = [
        {"kind": "note", "id": note["id"]},
        {"kind": "category", "id": second_category["id"]},
        {"kind": "category", "id": first_category["id"]},
    ]
    response = await client.post(
        f"/api/v1/projects/{project_id}/note-items/reorder-mixed",
        json={"parent_id": None, "ordered_items": ordered_items},
    )
    assert response.status_code == 200
    assert response.json() == {"updated_count": 3}

    tree = (await client.get(f"/api/v1/projects/{project_id}/notes")).json()
    actual = sorted(
        [
            *((item["order"], "category", item["id"]) for item in tree["categories"]),
            *((item["order"], "note", item["id"]) for item in tree["root_notes"]),
        ]
    )
    assert [(kind, item_id) for _, kind, item_id in actual] == [
        (item["kind"], item["id"]) for item in ordered_items
    ]

    incomplete = await client.post(
        f"/api/v1/projects/{project_id}/note-items/reorder-mixed",
        json={"parent_id": None, "ordered_items": ordered_items[:-1]},
    )
    assert incomplete.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("ordered_ids", [["x", "x"], ["x"]])
async def test_reorder_characters_rejects_duplicate_or_incomplete_ids(
    client: AsyncClient, ordered_ids: list[str]
) -> None:
    project_id = await _project(client, "角色排序校验")
    created = await client.post(f"/api/v1/projects/{project_id}/characters", data={"name": "甲"})
    actual_id = created.json()["id"]
    payload = {"ordered_ids": [actual_id, actual_id] if ordered_ids == ["x", "x"] else ["other"]}
    response = await client.post(f"/api/v1/projects/{project_id}/characters/reorder", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reorder_rejects_cross_project_id_and_wrong_parent(
    client: AsyncClient,
) -> None:
    first_project = await _project(client, "项目一")
    second_project = await _project(client, "项目二")
    character = await client.post(
        f"/api/v1/projects/{second_project}/characters", data={"name": "外部角色"}
    )
    response = await client.post(
        f"/api/v1/projects/{first_project}/characters/reorder",
        json={"ordered_ids": [character.json()["id"]]},
    )
    assert response.status_code == 400

    response = await client.post(
        f"/api/v1/projects/{first_project}/note-items/reorder",
        json={"kind": "note", "parent_id": "foreign-category", "ordered_ids": []},
    )
    assert response.status_code == 400
