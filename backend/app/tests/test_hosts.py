async def test_create_ssh_host_requires_secret(client):
    resp = await client.post(
        "/api/hosts",
        json={
            "label": "core-sw1",
            "protocol": "ssh",
            "hostname": "10.0.0.1",
            "auth_method": "password",
        },
    )
    assert resp.status_code == 422


async def test_create_ssh_host_with_password(client):
    resp = await client.post(
        "/api/hosts",
        json={
            "label": "core-sw1",
            "protocol": "ssh",
            "hostname": "10.0.0.1",
            "username": "admin",
            "auth_method": "password",
            "secret": "hunter2",
        },
    )
    assert resp.status_code == 201
    host = resp.json()
    assert host["port"] == 22
    assert host["has_secret"] is True
    assert "secret" not in host
    assert "secret_blob" not in host


async def test_telnet_host_defaults_port_and_allows_no_auth(client):
    resp = await client.post(
        "/api/hosts",
        json={"label": "old-switch", "protocol": "telnet", "hostname": "10.0.0.2"},
    )
    assert resp.status_code == 201
    assert resp.json()["port"] == 23
    assert resp.json()["has_secret"] is False


async def test_list_hosts_never_exposes_secret(client):
    await client.post(
        "/api/hosts",
        json={
            "label": "core-sw1",
            "protocol": "ssh",
            "hostname": "10.0.0.1",
            "auth_method": "password",
            "secret": "hunter2",
        },
    )
    resp = await client.get("/api/hosts")
    assert resp.status_code == 200
    body_text = resp.text
    assert "hunter2" not in body_text
    assert "secret_blob" not in body_text


async def test_update_host_replaces_secret(client):
    created = (
        await client.post(
            "/api/hosts",
            json={
                "label": "core-sw1",
                "protocol": "ssh",
                "hostname": "10.0.0.1",
                "auth_method": "password",
                "secret": "hunter2",
            },
        )
    ).json()

    resp = await client.patch(f"/api/hosts/{created['id']}", json={"secret": "new-pass"})
    assert resp.status_code == 200
    assert resp.json()["has_secret"] is True


async def test_move_host_between_folders(client):
    folder_a = (await client.post("/api/folders", json={"name": "A"})).json()
    folder_b = (await client.post("/api/folders", json={"name": "B"})).json()
    host = (
        await client.post(
            "/api/hosts",
            json={
                "label": "sw1",
                "folder_id": folder_a["id"],
                "protocol": "telnet",
                "hostname": "10.0.0.3",
            },
        )
    ).json()

    resp = await client.patch(f"/api/hosts/{host['id']}/move", json={"folder_id": folder_b["id"], "index": 0})
    assert resp.status_code == 200
    assert resp.json()["folder_id"] == folder_b["id"]


async def test_accept_host_key_only_for_ssh(client):
    telnet_host = (
        await client.post(
            "/api/hosts", json={"label": "sw1", "protocol": "telnet", "hostname": "10.0.0.4"}
        )
    ).json()

    resp = await client.post(
        f"/api/hosts/{telnet_host['id']}/accept-host-key", json={"fingerprint": "SHA256:abc"}
    )
    assert resp.status_code == 400


async def test_delete_host(client):
    host = (
        await client.post(
            "/api/hosts", json={"label": "sw1", "protocol": "telnet", "hostname": "10.0.0.5"}
        )
    ).json()

    resp = await client.delete(f"/api/hosts/{host['id']}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/hosts/{host['id']}")
    assert resp.status_code == 404
