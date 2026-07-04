async def test_create_and_list_folder(client):
    resp = await client.post("/api/folders", json={"name": "Lab"})
    assert resp.status_code == 201
    folder = resp.json()
    assert folder["name"] == "Lab"
    assert folder["parent_id"] is None

    resp = await client.get("/api/folders")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.json()] == ["Lab"]


async def test_nested_folder_and_rename(client):
    parent = (await client.post("/api/folders", json={"name": "Lab"})).json()
    child = await client.post("/api/folders", json={"name": "Rack1", "parent_id": parent["id"]})
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent["id"]

    renamed = await client.patch(f"/api/folders/{parent['id']}", json={"name": "Lab A"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Lab A"


async def test_move_folder_rejects_cycle(client):
    parent = (await client.post("/api/folders", json={"name": "Parent"})).json()
    child = (await client.post("/api/folders", json={"name": "Child", "parent_id": parent["id"]})).json()

    resp = await client.patch(
        f"/api/folders/{parent['id']}/move", json={"parent_id": child["id"], "index": 0}
    )
    assert resp.status_code == 400


async def test_delete_folder_cascades_to_children(client):
    parent = (await client.post("/api/folders", json={"name": "Parent"})).json()
    await client.post("/api/folders", json={"name": "Child", "parent_id": parent["id"]})

    resp = await client.delete(f"/api/folders/{parent['id']}")
    assert resp.status_code == 204

    remaining = (await client.get("/api/folders")).json()
    assert remaining == []


async def test_move_reorders_siblings(client):
    a = (await client.post("/api/folders", json={"name": "A"})).json()
    b = (await client.post("/api/folders", json={"name": "B"})).json()
    c = (await client.post("/api/folders", json={"name": "C"})).json()

    # Move C to the front.
    await client.patch(f"/api/folders/{c['id']}/move", json={"parent_id": None, "index": 0})

    ordered = (await client.get("/api/folders")).json()
    ordered_names = [f["name"] for f in sorted(ordered, key=lambda f: f["sort_order"])]
    assert ordered_names == ["C", "A", "B"]
