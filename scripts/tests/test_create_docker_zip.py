import unittest
from pathlib import Path

from scripts.create_docker_zip import PROJECT_ROOT, should_exclude


class CreateDockerZipTests(unittest.TestCase):
    def test_excludes_all_project_data_files(self):
        archive_path = PROJECT_ROOT / "MyManito-docker-test.zip"

        self.assertTrue(
            should_exclude(PROJECT_ROOT / "data/local-postgres/PG_VERSION", archive_path)
        )
        self.assertTrue(
            should_exclude(PROJECT_ROOT / "data/media/chat/image.png", archive_path)
        )
        self.assertTrue(
            should_exclude(PROJECT_ROOT / "data/static/admin/css/base.css", archive_path)
        )

    def test_excludes_all_project_tmp_files(self):
        archive_path = PROJECT_ROOT / "MyManito-docker-test.zip"

        self.assertTrue(
            should_exclude(PROJECT_ROOT / "tmp/chrome-team-7/Default/History", archive_path)
        )
        self.assertTrue(
            should_exclude(PROJECT_ROOT / "tmp/local-dev/backend.log", archive_path)
        )
        self.assertTrue(
            should_exclude(PROJECT_ROOT / "tmp/quizes_raw.md", archive_path)
        )

    def test_excludes_local_env_files_and_keeps_production_env_files(self):
        archive_path = PROJECT_ROOT / "MyManito-docker-test.zip"

        self.assertTrue(
            should_exclude(PROJECT_ROOT / "frontend/.env.development.local", archive_path)
        )
        self.assertTrue(
            should_exclude(PROJECT_ROOT / "backend/.env.local", archive_path)
        )
        self.assertFalse(should_exclude(PROJECT_ROOT / "frontend/.env", archive_path))
        self.assertFalse(should_exclude(PROJECT_ROOT / "backend/.env", archive_path))


if __name__ == "__main__":
    unittest.main()
