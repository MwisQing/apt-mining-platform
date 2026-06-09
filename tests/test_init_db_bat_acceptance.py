import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


FAKE_PSQL = r"""@echo off
echo %*>>psql_calls.log
echo password=%PGPASSWORD%>>psql_calls.log
echo %* | findstr /C:"SELECT 1 FROM pg_database" >nul
if not errorlevel 1 (
    if "%FAKE_DB_EXISTS%"=="1" echo 1
    exit /b 0
)
echo %* | findstr /C:"CREATE DATABASE" >nul
if not errorlevel 1 (
    if not "%FAKE_CREATE_EXIT%"=="" exit /b %FAKE_CREATE_EXIT%
    exit /b 0
)
exit /b 0
"""


class InitDbBatAcceptanceTest(unittest.TestCase):
    def run_init_db(self, db_exists):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            shutil.copy(ROOT / "init_db.bat", temp_root / "init_db.bat")
            migration_dir = temp_root / "backend_v2" / "migrations"
            migration_dir.mkdir(parents=True)
            (migration_dir / "001_initial.up.sql").write_text("-- test migration\n", encoding="utf-8")
            (temp_root / "psql.bat").write_text(FAKE_PSQL, encoding="utf-8")
            (temp_root / ".env").write_text(
                "\n".join(
                    [
                        "PG_BIN=psql.bat",
                        "APT_DB_HOST=10.1.2.3",
                        "APT_DB_PORT=6543",
                        "APT_DB_USER=app_user",
                        "APT_DB_PASSWORD=app_pass",
                        "APT_DB_NAME=target_db",
                        "APT_DB_ADMIN_USER=admin_user",
                        "APT_DB_ADMIN_PASSWORD=admin_pass",
                    ]
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PATH"] = f"{temp_root}{os.pathsep}{env.get('PATH', '')}"
            env["FAKE_DB_EXISTS"] = "1" if db_exists else "0"
            env.pop("PG_BIN", None)

            result = subprocess.run(
                ["cmd", "/c", "init_db.bat < nul"],
                cwd=temp_root,
                env=env,
                text=True,
                capture_output=True,
                timeout=10,
            )
            log = (temp_root / "psql_calls.log").read_text(encoding="utf-8")
            return result, log

    def test_creates_database_when_it_does_not_exist(self):
        result, log = self.run_init_db(db_exists=False)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CREATE DATABASE", log)
        self.assertIn("10.1.2.3", log)
        self.assertIn("6543", log)
        self.assertIn("admin_user", log)
        self.assertIn("password=admin_pass", log)
        self.assertIn("app_user", log)
        self.assertIn("password=app_pass", log)

    def test_skips_create_database_when_it_exists(self):
        result, log = self.run_init_db(db_exists=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("CREATE DATABASE", log)
        self.assertIn("target_db", log)


if __name__ == "__main__":
    unittest.main()
