from tests.conftest import auth_headers, make_user


def _create_ticket(client, headers, title="My issue", priority="medium"):
    return client.post(
        "/tickets/",
        json={"title": title, "description": "Details here", "priority": priority},
        headers=headers,
    )


def test_create_ticket(client):
    make_user(client, "tc@example.com")
    h = auth_headers(client, "tc@example.com")
    r = _create_ticket(client, h)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "My issue"
    assert data["status"] == "open"


def test_list_tickets_customer_sees_own(client):
    make_user(client, "c1@example.com")
    make_user(client, "c2@example.com")
    h1 = auth_headers(client, "c1@example.com")
    h2 = auth_headers(client, "c2@example.com")
    _create_ticket(client, h1, "Ticket for c1")
    _create_ticket(client, h2, "Ticket for c2")

    r = client.get("/tickets/", headers=h1)
    assert r.status_code == 200
    titles = [t["title"] for t in r.json()]
    assert "Ticket for c1" in titles
    assert "Ticket for c2" not in titles


def test_get_ticket_not_found(client):
    make_user(client, "notfound@example.com")
    h = auth_headers(client, "notfound@example.com")
    r = client.get("/tickets/99999", headers=h)
    assert r.status_code == 404


def test_update_ticket_status(client):
    make_user(client, "agent_t@example.com", role="agent")
    ha = auth_headers(client, "agent_t@example.com")

    make_user(client, "cust_t@example.com")
    hc = auth_headers(client, "cust_t@example.com")

    ticket = _create_ticket(client, hc).json()
    r = client.patch(f"/tickets/{ticket['id']}", json={"status": "in_progress"}, headers=ha)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_invalid_status_transition(client):
    make_user(client, "agent_inv@example.com", role="agent")
    ha = auth_headers(client, "agent_inv@example.com")
    make_user(client, "cust_inv@example.com")
    hc = auth_headers(client, "cust_inv@example.com")

    ticket = _create_ticket(client, hc).json()
    # Transition open → resolved is not allowed directly
    r = client.patch(f"/tickets/{ticket['id']}", json={"status": "resolved"}, headers=ha)
    assert r.status_code == 422


def test_reopen_closed_ticket_requires_reason(client):
    make_user(client, "agent_ro@example.com", role="agent")
    ha = auth_headers(client, "agent_ro@example.com")
    make_user(client, "cust_ro@example.com")
    hc = auth_headers(client, "cust_ro@example.com")

    ticket = _create_ticket(client, hc).json()
    tid = ticket["id"]
    client.patch(f"/tickets/{tid}", json={"status": "in_progress"}, headers=ha)
    client.patch(f"/tickets/{tid}", json={"status": "closed"}, headers=ha)

    r = client.patch(f"/tickets/{tid}", json={"status": "open"}, headers=ha)
    assert r.status_code == 422  # No reopen_reason

    r = client.patch(f"/tickets/{tid}", json={"status": "open", "reopen_reason": "customer follow-up"}, headers=ha)
    assert r.status_code == 200


def test_delete_ticket_agent_only(client):
    make_user(client, "del_agent@example.com", role="agent")
    ha = auth_headers(client, "del_agent@example.com")
    make_user(client, "del_cust@example.com")
    hc = auth_headers(client, "del_cust@example.com")

    ticket = _create_ticket(client, hc).json()
    # Customer cannot delete
    r = client.delete(f"/tickets/{ticket['id']}", headers=hc)
    assert r.status_code == 403
    # Agent can delete
    r = client.delete(f"/tickets/{ticket['id']}", headers=ha)
    assert r.status_code == 204


def test_filter_by_priority(client):
    make_user(client, "filt@example.com")
    h = auth_headers(client, "filt@example.com")
    _create_ticket(client, h, "Low prio", priority="low")
    _create_ticket(client, h, "High prio", priority="high")

    make_user(client, "fagent@example.com", role="agent")
    ha = auth_headers(client, "fagent@example.com")
    r = client.get("/tickets/?priority=low", headers=ha)
    assert r.status_code == 200
    priorities = [t["priority"] for t in r.json()]
    assert all(p == "low" for p in priorities)
