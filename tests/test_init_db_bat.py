from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_script():
    return (ROOT / "init_db.bat").read_text(encoding="utf-8")


class InitDbBatTest(unittest.TestCase):
    def test_init_db_uses_env_host_and_port(self):
        script = read_script()

        self.assertIn('set "PG_HOST=%APT_DB_HOST%"', script)
        self.assertIn('set "PG_PORT=%APT_DB_PORT%"', script)
        self.assertNotIn('set "PG_HOST=127.0.0.1"', script)
        self.assertNotIn('set "PG_PORT=5432"', script)

    def test_init_db_does_not_force_postgres_version_path(self):
        script = read_script()

        self.assertIn('set "PG_BIN=psql"', script)
        self.assertNotIn("C:\\Program Files\\PostgreSQL\\18\\bin\\psql.exe", script)

    def test_init_db_creates_database_when_query_returns_no_row(self):
        script = read_script()

        self.assertIn("DB_EXISTS", script)
        self.assertIn('-tAc "SELECT 1 FROM pg_database', script)
        self.assertIn('if "%DB_EXISTS%"=="1"', script)
        self.assertIn("CREATE DATABASE", script)

    def test_init_db_allows_empty_password_and_quotes_pgpassword(self):
        script = read_script()

        self.assertNotIn("password is empty", script.lower())
        self.assertIn('set "PGPASSWORD=%PG_PASS%"', script)
        self.assertNotIn("set PGPASSWORD=%PG_PASS%", script)

    def test_init_db_points_to_existing_start_command(self):
        script = read_script()

        self.assertNotIn("startGo.bat", script)
        self.assertIn("python start.py", script)


if __name__ == "__main__":
    unittest.main()
