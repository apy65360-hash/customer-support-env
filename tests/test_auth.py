from tests.conftest import auth_headers, make_user


def test_register_and_login(client):
    make_user(client, "a@example.com")
    headers = auth_headers(client, "a@example.com")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"


def test_duplicate_email(client):
    make_user(client, "dup@example.com")
    r = client.post("/auth/register", json={"email": "dup@example.com", "password": "x", "full_name": "X", "role": "customer"})
    assert r.status_code == 400


def test_bad_credentials(client):
    make_user(client, "bad@example.com")
    r = client.post("/auth/token", data={"username": "bad@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_update_me(client):
    make_user(client, "upd@example.com")
    headers = auth_headers(client, "upd@example.com")
    r = client.patch("/auth/me", json={"full_name": "Updated Name"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Updated Name"


def test_list_users_forbidden_for_customer(client):
    make_user(client, "cust@example.com")
    headers = auth_headers(client, "cust@example.com")
    r = client.get("/auth/users", headers=headers)
    assert r.status_code == 403


def test_list_users_allowed_for_admin(client):
    make_user(client, "admin@example.com", role="admin")
    headers = auth_headers(client, "admin@example.com")
    r = client.get("/auth/users", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
