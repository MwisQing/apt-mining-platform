from pathlib import Path
import unittest


class WorkbenchUiCopyTestCase(unittest.TestCase):
    def test_workbench_hero_copy_removed(self):
        content = Path("frontend/src/views/Workbench.vue").read_text(encoding="utf-8")
        self.assertNotIn("Priority Queue", content)
        self.assertNotIn("候选外联连接研判", content)
        self.assertNotIn("候选总数", content)
        self.assertNotIn("当前页高优先", content)
        self.assertNotIn("目标范围", content)

    def test_app_topbar_home_copy_removed(self):
        content = Path("frontend/src/App.vue").read_text(encoding="utf-8")
        self.assertNotIn("Threat Hunting", content)
        self.assertNotIn("围绕高优先候选外联连接，集中完成筛选、标记和事件收敛。", content)
        self.assertNotIn("Local-first", content)


if __name__ == "__main__":
    unittest.main()
