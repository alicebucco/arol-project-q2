-- Authentication migration: passwords are stored only as bcrypt hashes.
-- The hashes are populated locally by db/scripts/set_development_passwords.py.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
