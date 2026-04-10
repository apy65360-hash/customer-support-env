from tests.conftest import auth_headers, make_user


def _agent_headers(client, email="kb_agent@example.com"):
    make_user(client, email, role="agent")
    return auth_headers(client, email)


def test_create_and_get_article(client):
    ha = _agent_headers(client)
    r = client.post("/kb/articles", json={"title": "Reset password", "body": "Go to settings...", "tags": "password,reset"}, headers=ha)
    assert r.status_code == 201
    art = r.json()
    assert art["title"] == "Reset password"

    r2 = client.get(f"/kb/articles/{art['id']}", headers=ha)
    assert r2.status_code == 200
    assert r2.json()["id"] == art["id"]


def test_list_articles(client):
    ha = _agent_headers(client, "kb_agent2@example.com")
    client.post("/kb/articles", json={"title": "Article A", "body": "Body A"}, headers=ha)
    client.post("/kb/articles", json={"title": "Article B", "body": "Body B"}, headers=ha)
    r = client.get("/kb/articles", headers=ha)
    assert r.status_code == 200
    assert len(r.json()) >= 2


def test_suggest_articles(client):
    ha = _agent_headers(client, "kb_agent3@example.com")
    client.post("/kb/articles", json={"title": "Password reset guide", "body": "Steps to reset...", "tags": "password"}, headers=ha)

    r = client.get("/kb/articles/suggest?text=forgot+my+password+help", headers=ha)
    assert r.status_code == 200
    # The password article should be suggested
    titles = [a["title"] for a in r.json()]
    assert any("password" in t.lower() for t in titles)


def test_link_article_to_ticket(client):
    ha = _agent_headers(client, "kb_agent4@example.com")
    make_user(client, "kb_cust@example.com")
    hc = auth_headers(client, "kb_cust@example.com")

    ticket = client.post("/tickets/", json={"title": "T", "description": "D"}, headers=hc).json()
    art = client.post("/kb/articles", json={"title": "Guide", "body": "Content"}, headers=ha).json()

    r = client.post(f"/kb/tickets/{ticket['id']}/link/{art['id']}", headers=ha)
    assert r.status_code == 200
    assert r.json()["ticket_id"] == ticket["id"]
    assert r.json()["article_id"] == art["id"]


def test_customer_cannot_create_article(client):
    make_user(client, "kb_cust2@example.com")
    hc = auth_headers(client, "kb_cust2@example.com")
    r = client.post("/kb/articles", json={"title": "Hack", "body": "..."}, headers=hc)
    assert r.status_code == 403
