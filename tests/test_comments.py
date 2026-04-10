from tests.conftest import auth_headers, make_user


def _setup_ticket(client):
    make_user(client, "cm_cust@example.com")
    make_user(client, "cm_agent@example.com", role="agent")
    hc = auth_headers(client, "cm_cust@example.com")
    ha = auth_headers(client, "cm_agent@example.com")
    ticket = client.post(
        "/tickets/",
        json={"title": "Comment ticket", "description": "Desc", "priority": "low"},
        headers=hc,
    ).json()
    return ticket["id"], hc, ha


def test_add_comment_customer(client):
    tid, hc, ha = _setup_ticket(client)
    r = client.post(f"/tickets/{tid}/comments/", json={"body": "Hello"}, headers=hc)
    assert r.status_code == 201
    assert r.json()["body"] == "Hello"
    assert r.json()["is_internal"] is False


def test_internal_note_hidden_from_customer(client):
    tid, hc, ha = _setup_ticket(client)
    # Agent adds internal note
    r = client.post(f"/tickets/{tid}/comments/", json={"body": "Internal note", "is_internal": True}, headers=ha)
    assert r.status_code == 201

    # Customer listing should NOT see internal notes
    r = client.get(f"/tickets/{tid}/comments/", headers=hc)
    assert r.status_code == 200
    bodies = [c["body"] for c in r.json()]
    assert "Internal note" not in bodies


def test_internal_note_visible_to_agent(client):
    tid, hc, ha = _setup_ticket(client)
    client.post(f"/tickets/{tid}/comments/", json={"body": "Secret note", "is_internal": True}, headers=ha)

    r = client.get(f"/tickets/{tid}/comments/", headers=ha)
    assert r.status_code == 200
    bodies = [c["body"] for c in r.json()]
    assert "Secret note" in bodies


def test_customer_cannot_post_internal_note(client):
    tid, hc, ha = _setup_ticket(client)
    r = client.post(f"/tickets/{tid}/comments/", json={"body": "Sneaky", "is_internal": True}, headers=hc)
    assert r.status_code == 403
