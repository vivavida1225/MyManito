import unittest
from pathlib import Path

from scripts.create_docker_zip import PROJECT_ROOT, should_exclude


class CreateDockerZipTests(unittest.TestCase):
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
