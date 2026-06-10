"""Authentication and role-access tests."""


def test_anonymous_is_redirected_to_login(anon):
    r = anon.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert anon.get("/invoices", follow_redirects=False).status_code == 303
    # Public endpoints stay open.
    assert anon.get("/login").status_code == 200
    assert anon.get("/health").status_code == 200


def test_bad_credentials_rejected(anon):
    r = anon.post("/login", data={"username": "admin", "password": "nope"},
                  follow_redirects=False)
    assert r.status_code == 200
    assert "Invalid username or password" in r.text


def test_admin_can_reach_user_admin(client):
    assert client.get("/users", follow_redirects=False).status_code == 200


def test_staff_blocked_from_user_admin(client, anon):
    # Admin creates a staff user, then that user is blocked from /users.
    client.post("/users/new", data={"username": "staff1", "full_name": "Staff One",
                                    "role": "staff", "password": "pw12345",
                                    "permissions": ["invoicing"]})
    anon.post("/login", data={"username": "staff1", "password": "pw12345"})
    r = anon.get("/users", follow_redirects=False)
    assert r.status_code == 303                       # admin-only: redirected away
    assert anon.get("/invoices", follow_redirects=False).status_code == 200  # granted area works


def test_logout_clears_session(client):
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303
