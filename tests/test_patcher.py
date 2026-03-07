"""
补丁应用与回滚器的单元测试
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.core.exceptions import PatchApplyError, PatchRollbackError
from src.repair.models import FileBackup, FixPlan, PatchInfo, RiskLevel
from src.repair.patcher import PatchApplier


@pytest.fixture
def tmp_project(tmp_path):
    """创建临时项目目录结构。"""
    # 创建一个简单的源码文件
    app_file = tmp_path / "src" / "app.js"
    app_file.parent.mkdir(parents=True)
    app_file.write_text(
        'function login() {\n'
        '  const nmae = "admin";\n'
        '  console.log(nmae);\n'
        '}\n',
        encoding="utf-8",
    )

    style_file = tmp_path / "src" / "style.css"
    style_file.write_text(
        'body {\n'
        '  color: red;\n'
        '  font-size: 14px;\n'
        '}\n',
        encoding="utf-8",
    )

    return tmp_path


class TestPatchApply:
    """补丁应用测试。"""

    def test_apply_single_patch(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="src/app.js",
                    old_code='const nmae = "admin"',
                    new_code='const name = "admin"',
                ),
            ],
        )

        backups = applier.apply(plan)
        assert len(backups) == 1

        # 验证文件已被修改
        content = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")
        assert 'const name = "admin"' in content
        assert 'const nmae = "admin"' not in content

    def test_apply_multiple_patches(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="src/app.js",
                    old_code='const nmae = "admin"',
                    new_code='const name = "admin"',
                ),
                PatchInfo(
                    file_path="src/style.css",
                    old_code="color: red",
                    new_code="color: blue",
                ),
            ],
        )

        backups = applier.apply(plan)
        assert len(backups) == 2

        js_content = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")
        css_content = (tmp_project / "src" / "style.css").read_text(encoding="utf-8")
        assert 'const name = "admin"' in js_content
        assert "color: blue" in css_content

    def test_apply_empty_patches(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(can_fix=True, patches=[])
        backups = applier.apply(plan)
        assert backups == []

    def test_apply_nonexistent_file_raises(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="nonexistent.js",
                    old_code="x",
                    new_code="y",
                ),
            ],
        )
        with pytest.raises(PatchApplyError, match="不存在"):
            applier.apply(plan)

    def test_apply_no_match_raises(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="src/app.js",
                    old_code="THIS CODE DOES NOT EXIST",
                    new_code="replacement",
                ),
            ],
        )
        with pytest.raises(PatchApplyError, match="未找到匹配"):
            applier.apply(plan)

    def test_apply_rollback_on_failure(self, tmp_project):
        """第二个补丁失败时，第一个应该被回滚。"""
        applier = PatchApplier(str(tmp_project))
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="src/app.js",
                    old_code='const nmae = "admin"',
                    new_code='const name = "admin"',
                ),
                PatchInfo(
                    file_path="src/app.js",
                    old_code="THIS DOES NOT EXIST",
                    new_code="whatever",
                ),
            ],
        )

        with pytest.raises(PatchApplyError):
            applier.apply(plan)

        # 验证文件已回滚到原始状态
        content = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")
        assert 'const nmae = "admin"' in content


class TestPatchRollback:
    """补丁回滚测试。"""

    def test_rollback_restores_files(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        original = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")

        # 先应用补丁
        plan = FixPlan(
            can_fix=True,
            patches=[
                PatchInfo(
                    file_path="src/app.js",
                    old_code='const nmae = "admin"',
                    new_code='const name = "admin"',
                ),
            ],
        )
        backups = applier.apply(plan)

        # 回滚
        applier.rollback(backups)

        # 验证回滚后与原始一致
        restored = (tmp_project / "src" / "app.js").read_text(encoding="utf-8")
        assert restored == original

    def test_rollback_empty_list(self, tmp_project):
        applier = PatchApplier(str(tmp_project))
        # 空列表不应抛异常
        applier.rollback([])
