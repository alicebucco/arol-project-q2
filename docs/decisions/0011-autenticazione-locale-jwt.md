# 0011 — Local authentication with hashed passwords and JWT

## Decision

For the project's local environment, we use login with `user_id` and password,
bcrypt hashes in the database, and short-lived signed JWTs (`HS256`). The
frontend sends the token only in the `Authorization: Bearer` header;
`X-User-Id` is no longer an authentication mechanism.

## Rationale

The synthetic dataset contains users, companies and roles, but no passwords or
identity provider. This solution removes impersonation through a simple header
without requiring external accounts or infrastructure.

## Consequences

- `AUTH_JWT_SECRET` and `AUTH_DEVELOPMENT_PASSWORD` remain in the local
  `.env`, which is excluded from Git.
- `db/scripts/set_development_passwords.py` creates hashes for synthetic users
  without committing clear-text passwords.
- The token identifies the user, while company and visibility are read again
  from the database for every request to preserve authorisation checks.
- A production deployment still requires HTTPS, rate limiting, secret
  rotation, password/reset management and preferably an identity provider.
