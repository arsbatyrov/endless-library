"""AUTH-011: the OpenAPI contract describes security, and the running API behaves exactly as the contract says.

Closed by default: every operation must be either in the explicit list of open operations or declare the bearer
scheme and the 401 answer. A new endpoint added without protection (or without documentation) fails here.
For every protected operation the real answers are checked: no token and a bad token give 401, a reader token gives
403 where the contract documents 403 and never where it does not, an admin token is never refused.
"""

import pytest

from app.auth.tokens import create_access_token
from tests.factories import make_user


@pytest.fixture
def client(anonymous_client):
    """These tests check sign-in, roles and access errors: they start WITHOUT a login."""
    return anonymous_client


pytestmark = pytest.mark.contract

# The only operations that need no bearer token: probes, and the cookie-based session endpoints.
OPEN_OPERATIONS = {
    ("GET", "/health"),
    ("GET", "/ready"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
}
UNKNOWN_ID = "999999"  # no such record, and not the reader card of the test reader


@pytest.fixture
def spec(client):
    return client.get("/openapi.json").json()


def operations(spec):
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            yield method.upper(), path, operation


def protected(spec):
    return [(m, p, op) for m, p, op in operations(spec) if (m, p) not in OPEN_OPERATIONS]


def ident(case):
    return f"{case[0]} {case[1]}"


def concrete_path(path: str) -> str:
    out = path
    while "{" in out:
        start, end = out.index("{"), out.index("}")
        out = out[:start] + UNKNOWN_ID + out[end + 1 :]
    return out


def send(client, method, path, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, concrete_path(path), json=body, headers=headers)


def token_for(db, role):
    user = make_user(db, role=role)
    return create_access_token(user.id, user.role)


# ---------- criterion 1: the security scheme and the 401/403 answers ----------


def test_the_bearer_scheme_is_declared(spec):
    assert spec["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }


def test_open_operations_exist_and_declare_no_security(spec):
    found = {(m, p): op for m, p, op in operations(spec)}

    for key in OPEN_OPERATIONS:
        assert key in found, f"{key} is listed as open but does not exist any more"
        assert not found[key].get("security"), f"{key} must not demand a bearer token"


def test_every_other_operation_declares_the_bearer_scheme_and_401(spec):
    for method, path, operation in protected(spec):
        assert operation.get("security") == [{"HTTPBearer": []}], (
            f"{method} {path} is not marked as protected"
        )
        assert "401" in operation["responses"], f"{method} {path} does not document 401"


def test_the_list_of_operations_is_complete_so_nothing_slips_through(spec):
    """A guard against forgetting to classify a new endpoint: the count of operations is pinned."""
    assert len(list(operations(spec))) == 25


# ---------- criterion 3: separate 401 and 403 checks against the running API ----------


def test_no_token_is_401_for_every_protected_operation(client, spec):
    for method, path, _ in protected(spec):
        response = send(client, method, path)
        assert response.status_code == 401, f"{method} {path}"
        assert response.headers["www-authenticate"] == "Bearer", f"{method} {path}"


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "x" * 400])
def test_a_bad_token_is_401_for_every_protected_operation(client, spec, token):
    for method, path, _ in protected(spec):
        assert send(client, method, path, token).status_code == 401, f"{method} {path}"


def test_a_reader_gets_403_exactly_where_the_contract_documents_403(client, db, spec):
    token = token_for(db, "reader")

    for method, path, operation in protected(spec):
        status = send(client, method, path, token).status_code
        documented = "403" in operation["responses"]
        assert status != 401, (
            f"{method} {path}: a valid reader token must not be refused as unauthenticated"
        )
        if documented:
            assert status == 403, f"{method} {path} documents 403 but a reader got {status}"
        else:
            assert status != 403, (
                f"{method} {path} gave a reader 403 that the contract does not mention"
            )


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_staff_is_never_refused_by_the_contract_paths(client, db, spec, role):
    token = token_for(db, role)

    for method, path, _ in protected(spec):
        status = send(client, method, path, token).status_code
        assert status != 401, f"{method} {path}"
        # staff-only operations that a librarian may use must not answer 403 (user management has its own rules)
        if not path.startswith("/users"):
            assert status != 403, f"{method} {path} refused a {role}"


def test_the_responses_of_documented_401_and_403_have_the_documented_shape(client, db, spec):
    unauthenticated = send(client, "GET", "/books")
    forbidden = send(client, "POST", "/books", token_for(db, "reader"))

    assert set(unauthenticated.json()) == {"detail"}
    assert set(forbidden.json()) == {"detail"}


# ---------- criterion 2: /auth/* and /users are fully described ----------


def schemas(spec):
    return spec["components"]["schemas"]


def test_models_of_auth_and_users_are_described(spec):
    for name in (
        "LoginRequest",
        "LoginResponse",
        "MeResponse",
        "PasswordChangeRequest",
        "UserCreate",
        "UserRead",
        "UserUpdate",
        "PasswordReset",
    ):
        assert name in schemas(spec), name


def test_user_read_never_declares_a_password_field(spec):
    properties = schemas(spec)["UserRead"]["properties"]

    assert not any("password" in name or "hash" in name for name in properties)
    assert set(properties) == {
        "id",
        "username",
        "role",
        "reader_id",
        "is_active",
        "created_at",
        "last_login_at",
    }


def test_password_length_limits_are_in_the_schema(spec):
    assert schemas(spec)["UserCreate"]["properties"]["password"]["minLength"] == 8
    assert schemas(spec)["UserCreate"]["properties"]["password"]["maxLength"] == 128
    assert schemas(spec)["PasswordReset"]["properties"]["new_password"]["minLength"] == 8
    assert schemas(spec)["LoginRequest"]["properties"]["password"]["maxLength"] == 128


def test_roles_are_an_enum_in_the_schema(spec):
    assert schemas(spec)["UserCreate"]["properties"]["role"]["enum"] == [
        "reader",
        "librarian",
        "admin",
    ]


def test_login_documents_the_cookie_and_the_lockout(spec):
    login = spec["paths"]["/auth/login"]["post"]["responses"]

    assert "Set-Cookie" in login["200"]["headers"]
    assert "Retry-After" in login["429"]["headers"]
    assert {"400", "401", "422", "429"} <= set(login)


def test_refresh_documents_the_cookie_in_and_out(spec):
    operation = spec["paths"]["/auth/refresh"]["post"]

    cookie_params = [p for p in operation.get("parameters", []) if p["in"] == "cookie"]
    assert [p["name"] for p in cookie_params] == ["refresh_token"]
    assert "Set-Cookie" in operation["responses"]["200"]["headers"]
    assert "Set-Cookie" in operation["responses"]["401"]["headers"]


def test_logout_and_password_change_document_that_the_cookie_is_cleared(spec):
    assert "Set-Cookie" in spec["paths"]["/auth/logout"]["post"]["responses"]["204"]["headers"]
    assert "Set-Cookie" in spec["paths"]["/auth/password"]["post"]["responses"]["204"]["headers"]


def test_users_operations_document_every_business_error(spec):
    codes = {
        (m, p): set(op["responses"]) for m, p, op in operations(spec) if p.startswith("/users")
    }

    assert {"201", "400", "401", "403", "404", "409", "422"} <= codes[("POST", "/users")]
    assert {"200", "400", "401", "403", "404", "409", "422"} <= codes[("PATCH", "/users/{user_id}")]
    assert {"204", "401", "403", "404", "422"} <= codes[("POST", "/users/{user_id}/reset-password")]
    assert {"200", "401", "403"} <= codes[("GET", "/users")]


def test_the_cookie_is_the_only_credential_the_session_endpoints_take(spec):
    """No operation takes a refresh token in a body or a query: it can only travel in the httpOnly cookie."""
    for method, path, operation in operations(spec):
        for parameter in operation.get("parameters", []):
            if "refresh" in parameter["name"]:
                assert parameter["in"] == "cookie", f"{method} {path}"
        assert "refresh" not in str(operation.get("requestBody", ""))
