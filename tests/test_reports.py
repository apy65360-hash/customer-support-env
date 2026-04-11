from tests.conftest import auth_headers, make_user


def _create_ticket_and_resolve(client, cust_h, agent_h):
    ticket = client.post(
        "/tickets/",
        json={"title": "T", "description": "D", "priority": "high"},
        headers=cust_h,
    ).json()
    tid = ticket["id"]
    client.patch(f"/tickets/{tid}", json={"status": "in_progress"}, headers=agent_h)
    client.patch(f"/tickets/{tid}", json={"status": "resolved"}, headers=agent_h)
    return ticket


def test_summary(client):
    make_user(client, "rpt_agent@example.com", role="agent")
    ha = auth_headers(client, "rpt_agent@example.com")
    make_user(client, "rpt_cust@example.com")
    hc = auth_headers(client, "rpt_cust@example.com")

    _create_ticket_and_resolve(client, hc, ha)

    r = client.get("/reports/summary", headers=ha)
    assert r.status_code == 200
    data = r.json()
    assert "resolved" in data


def test_resolution_time(client):
    make_user(client, "rt_agent@example.com", role="agent")
    ha = auth_headers(client, "rt_agent@example.com")
    make_user(client, "rt_cust@example.com")
    hc = auth_headers(client, "rt_cust@example.com")

    _create_ticket_and_resolve(client, hc, ha)

    r = client.get("/reports/resolution-time", headers=ha)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_agent_performance(client):
    make_user(client, "ap_agent@example.com", role="agent")
    ha = auth_headers(client, "ap_agent@example.com")

    r = client.get("/reports/agent-performance", headers=ha)
    assert r.status_code == 200
    agents = r.json()
    assert isinstance(agents, list)
    emails = [a["email"] for a in agents]
    assert "ap_agent@example.com" in emails


def test_overdue(client):
    make_user(client, "od_agent@example.com", role="agent")
    ha = auth_headers(client, "od_agent@example.com")

    r = client.get("/reports/overdue", headers=ha)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_reports_forbidden_for_customer(client):
    make_user(client, "cust_report@example.com")
    hc = auth_headers(client, "cust_report@example.com")
    r = client.get("/reports/summary", headers=hc)
    assert r.status_code == 403
