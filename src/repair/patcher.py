"""
补丁应用与回滚器

PatchApplier 负责：
1. 备份原始文件
2. 应用代码补丁（字符串替换）
3. 修复失败时回滚到备份
"""

from pathlib import Path
from typing import Optional

from loguru import logger

from src.core.exceptions import PatchApplyError, PatchRollbackError
from src.repair.models import FileBackup, FixPlan, PatchInfo


class PatchApplier:
    """补丁应用与回滚器。

    典型使用：
        applier = PatchApplier(project_path="/path/to/project")
        backups = applier.apply(fix_plan)
        # 如果重测失败
        applier.rollback(backups)
    """

    def __init__(self, project_path: str) -> None:
        self._project_path = Path(project_path)

    def apply(self, plan: FixPlan) -> list[FileBackup]:
        """应用修复方案中的所有补丁。

        先备份所有涉及的文件，再逐个应用补丁。
        如果某个补丁应用失败，自动回滚已应用的补丁。

        Args:
            plan: AI 生成的修复方案

        Returns:
            list[FileBackup]: 文件备份列表（用于后续回滚）

        Raises:
            PatchApplyError: 补丁应用失败
        """
        if not plan.patches:
            logger.info("修复方案无补丁，跳过")
            return []

        # 阶段1：备份所有涉及的文件
        backups = self._backup_files(plan.patches)

        # 阶段2：逐个应用补丁
        applied_count = 0
        try:
            for i, patch in enumerate(plan.patches):
                self._apply_single_patch(patch)
                applied_count += 1
                logger.info(
                    "  补丁 {}/{} 已应用 | {} | {}",
                    i + 1, len(plan.patches),
                    patch.file_path, patch.description,
                )
        except PatchApplyError:
            # 应用失败，回滚已应用的补丁
            logger.warning(
                "补丁应用失败（第{}/{}个），回滚所有更改",
                applied_count + 1, len(plan.patches),
            )
            self.rollback(backups)
            raise

        logger.info("所有补丁应用完成 | 共 {} 个", len(plan.patches))
        return backups

    def rollback(self, backups: list[FileBackup]) -> None:
        """回滚所有文件到备份版本。

        Args:
            backups: 文件备份列表

        Raises:
            PatchRollbackError: 回滚失败
        """
        if not backups:
            return

        logger.info("回滚文件 | 共 {} 个", len(backups))
        errors: list[str] = []

        for backup in backups:
            try:
                path = Path(backup.file_path)
                path.write_text(backup.original_content, encoding="utf-8")
                logger.debug("  已回滚: {}", backup.file_path)
            except Exception as e:
                err = f"回滚失败 {backup.file_path}: {e}"
                logger.error(err)
                errors.append(err)

        if errors:
            raise PatchRollbackError(
                message=f"部分文件回滚失败（{len(errors)}/{len(backups)}）",
                detail="; ".join(errors),
            )

        logger.info("文件回滚完成")

    def _backup_files(self, patches: list[PatchInfo]) -> list[FileBackup]:
        """备份所有涉及的文件。"""
        backups: list[FileBackup] = []
        seen_paths: set[str] = set()

        for patch in patches:
            abs_path = self._resolve_path(patch.file_path)
            path_str = str(abs_path)

            if path_str in seen_paths:
                continue
            seen_paths.add(path_str)

            if not abs_path.exists():
                raise PatchApplyError(
                    message=f"补丁目标文件不存在: {patch.file_path}",
                    detail=f"绝对路径: {abs_path}",
                )

            try:
                content = abs_path.read_text(encoding="utf-8")
                backups.append(FileBackup(
                    file_path=path_str,
                    original_content=content,
                ))
            except Exception as e:
                raise PatchApplyError(
                    message=f"无法读取文件: {patch.file_path}",
                    detail=str(e),
                )

        return backups

    def _apply_single_patch(self, patch: PatchInfo) -> None:
        """应用单个补丁。"""
        abs_path = self._resolve_path(patch.file_path)

        try:
            content = abs_path.read_text(encoding="utf-8")
        except Exception as e:
            raise PatchApplyError(
                message=f"无法读取文件: {patch.file_path}",
                detail=str(e),
            )

        if patch.old_code not in content:
            raise PatchApplyError(
                message=f"在 {patch.file_path} 中未找到匹配的代码片段",
                detail=f"old_code 前50字符: {patch.old_code[:50]}...",
            )

        # 执行替换（只替换第一处匹配）
        new_content = content.replace(patch.old_code, patch.new_code, 1)

        try:
            abs_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            raise PatchApplyError(
                message=f"无法写入文件: {patch.file_path}",
                detail=str(e),
            )

    def _resolve_path(self, file_path: str) -> Path:
        """将相对路径解析为绝对路径。"""
        p = Path(file_path)
        if p.is_absolute():
            return p
        return self._project_path / p
