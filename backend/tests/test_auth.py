import pytest
from fastapi import HTTPException

from core.auth import AuthContext, ensure_company_access, ensure_visibility


@pytest.mark.parametrize(
    ("visibility", "domain", "allowed"),
    [
        ("full", "machines", True),
        ("full", "operational", True),
        ("full", "commercial", True),
        ("technician", "machines", True),
        ("technician", "operational", True),
        ("technician", "commercial", False),
        ("commercial", "machines", True),
        ("commercial", "operational", False),
        ("commercial", "manuals", True),
    ],
)
def test_visibility_matrix(visibility: str, domain: str, allowed: bool) -> None:
    user = AuthContext("USR-TEST", "CMP-001", visibility)
    if allowed:
        ensure_visibility(user, domain)
    else:
        with pytest.raises(HTTPException, match="Access denied") as error:
            ensure_visibility(user, domain)
        assert error.value.status_code == 403


def test_company_boundary_is_enforced() -> None:
    user = AuthContext("USR-TEST", "CMP-001", "full")
    ensure_company_access(user, "CMP-001")

    with pytest.raises(HTTPException, match="Access denied") as error:
        ensure_company_access(user, "CMP-002")
    assert error.value.status_code == 403
