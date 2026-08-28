"""Set bcrypt hashes for synthetic local users without committing a password."""

import os
import sys

import bcrypt
import psycopg


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def main() -> None:
    password = required("AUTH_DEVELOPMENT_PASSWORD")
    if len(password) < 8:
        raise RuntimeError("AUTH_DEVELOPMENT_PASSWORD must be at least 8 characters long.")

    connection_string = (
        f"host={required('POSTGRES_HOST')} port={os.getenv('POSTGRES_PORT', '5432')} "
        f"user={required('POSTGRES_USER')} password={required('POSTGRES_PASSWORD')} "
        f"dbname={required('POSTGRES_DB')}"
    )
    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cursor.execute("SELECT user_id FROM users ORDER BY user_id")
            user_ids = [row[0] for row in cursor.fetchall()]
            for user_id in user_ids:
                password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                cursor.execute(
                    "UPDATE users SET password_hash = %s WHERE user_id = %s",
                    (password_hash, user_id),
                )
        conn.commit()
    print(f"Password hash set for {len(user_ids)} local synthetic users.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
