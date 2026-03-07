"""
记忆存储引擎

基于 SQLite 的轻量级记忆系统，无需外部服务依赖：
1. 测试历史 — 每次测试的完整记录（URL、步骤、Bug、报告）
2. 测试经验 — AI 从历史中总结的经验教训（哪些选择器常失败、哪类页面容易出Bug）
3. 页面指纹 — 记住已测过的页面，避免重复测试相同内容
4. Bug模式 — 结构化Bug指纹，从BugReport固定字段直接提取（v1.3）
5. 修复经验 — Bug发现 + 修复方案的完整经验，字段化存储（v1.3）

设计原则：
- 零外部依赖（只用 Python 内置的 sqlite3）
- 数据存在项目 data/ 目录下，不会丢失
- 支持按 URL、时间、通过率等维度查询历史
- 记忆从结构化字段直接提取，规则明确，零AI成本（v1.3）
- 淘汰机制：原始记录30天过期，同URL摘要最多保留10条（v1.3）
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from src.core.config import PROJECT_ROOT


# 数据库文件路径
DB_PATH = PROJECT_ROOT / "data" / "memory.db"


class MemoryStore:
    """SQLite 记忆存储。

    典型使用：
        store = MemoryStore()
        store.save_test_result(report)
        history = store.get_history(url="http://localhost:3000")
        experiences = store.get_experiences(category="selector")
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """初始化记忆存储。

        Args:
            db_path: 数据库文件路径，默认使用项目 data/memory.db
        """
        self._db_path = db_path or DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构。"""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS test_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT DEFAULT '',
                total_steps INTEGER DEFAULT 0,
                passed_steps INTEGER DEFAULT 0,
                failed_steps INTEGER DEFAULT 0,
                bug_count INTEGER DEFAULT 0,
                pass_rate REAL DEFAULT 0.0,
                duration_seconds REAL DEFAULT 0.0,
                report_markdown TEXT DEFAULT '',
                steps_json TEXT DEFAULT '[]',
                bugs_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source_test_id INTEGER,
                relevance_score REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (source_test_id) REFERENCES test_history(id)
            );

            CREATE TABLE IF NOT EXISTS page_fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                url_pattern TEXT DEFAULT '',
                last_tested_at TEXT NOT NULL,
                test_count INTEGER DEFAULT 1,
                avg_pass_rate REAL DEFAULT 0.0,
                known_issues TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS bug_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT DEFAULT '',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                location TEXT DEFAULT '',
                hit_count INTEGER DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                is_resolved INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS fix_experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                bug_fingerprint TEXT NOT NULL,
                bug_title TEXT NOT NULL,
                bug_severity TEXT NOT NULL,
                bug_category TEXT DEFAULT '',
                bug_description TEXT DEFAULT '',
                fix_analysis TEXT DEFAULT '',
                fix_patches_json TEXT DEFAULT '[]',
                fix_confidence REAL DEFAULT 0.0,
                fix_risk_level TEXT DEFAULT 'medium',
                fix_verified INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_history_url ON test_history(url);
            CREATE INDEX IF NOT EXISTS idx_history_created ON test_history(created_at);
            CREATE INDEX IF NOT EXISTS idx_exp_category ON experiences(category);
            CREATE INDEX IF NOT EXISTS idx_fp_url ON page_fingerprints(url);
            CREATE INDEX IF NOT EXISTS idx_bp_url ON bug_patterns(url);
            CREATE INDEX IF NOT EXISTS idx_bp_fingerprint ON bug_patterns(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_fe_url ON fix_experiences(url);
            CREATE INDEX IF NOT EXISTS idx_fe_fingerprint ON fix_experiences(bug_fingerprint);
        """)
        self._conn.commit()
        logger.debug("记忆存储初始化完成 | 路径={}", self._db_path)

    def save_test_result(
        self,
        test_name: str,
        url: str,
        description: str = "",
        total_steps: int = 0,
        passed_steps: int = 0,
        failed_steps: int = 0,
        bug_count: int = 0,
        pass_rate: float = 0.0,
        duration_seconds: float = 0.0,
        report_markdown: str = "",
        steps_json: str = "[]",
        bugs_json: str = "[]",
    ) -> int:
        """保存测试结果到历史记录。

        Returns:
            int: 新记录的 ID
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO test_history
               (test_name, url, description, total_steps, passed_steps,
                failed_steps, bug_count, pass_rate, duration_seconds,
                report_markdown, steps_json, bugs_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (test_name, url, description, total_steps, passed_steps,
             failed_steps, bug_count, pass_rate, duration_seconds,
             report_markdown, steps_json, bugs_json, now),
        )
        self._conn.commit()
        record_id = cursor.lastrowid
        logger.info("测试结果已保存 | ID={} | URL={} | 通过率={:.0%}", record_id, url, pass_rate)

        # 更新页面指纹
        self._update_fingerprint(url, pass_rate)

        return record_id

    def get_history(
        self,
        url: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """查询测试历史。

        Args:
            url: 按 URL 过滤（模糊匹配）
            limit: 最多返回条数

        Returns:
            list[dict]: 历史记录列表
        """
        if url:
            rows = self._conn.execute(
                """SELECT * FROM test_history
                   WHERE url LIKE ? ORDER BY created_at DESC LIMIT ?""",
                (f"%{url}%", limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM test_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]

    def save_experience(
        self,
        category: str,
        content: str,
        source_test_id: Optional[int] = None,
        relevance_score: float = 1.0,
    ) -> int:
        """保存测试经验。

        Args:
            category: 经验类别（selector/bug_pattern/page_type/timing 等）
            content: 经验内容
            source_test_id: 来源测试记录ID
            relevance_score: 相关性评分

        Returns:
            int: 新记录的 ID
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """INSERT INTO experiences
               (category, content, source_test_id, relevance_score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (category, content, source_test_id, relevance_score, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_experiences(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询测试经验。

        Args:
            category: 按类别过滤
            limit: 最多返回条数

        Returns:
            list[dict]: 经验列表
        """
        if category:
            rows = self._conn.execute(
                """SELECT * FROM experiences
                   WHERE category = ? ORDER BY relevance_score DESC, created_at DESC
                   LIMIT ?""",
                (category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT * FROM experiences
                   ORDER BY relevance_score DESC, created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        return [dict(r) for r in rows]

    def get_page_fingerprint(self, url: str) -> Optional[dict]:
        """获取页面指纹信息。

        Args:
            url: 页面 URL

        Returns:
            dict or None: 页面指纹信息
        """
        row = self._conn.execute(
            "SELECT * FROM page_fingerprints WHERE url = ?", (url,),
        ).fetchone()
        return dict(row) if row else None

    def get_stats(self) -> dict:
        """获取记忆系统统计信息。"""
        history_count = self._conn.execute(
            "SELECT COUNT(*) FROM test_history",
        ).fetchone()[0]
        experience_count = self._conn.execute(
            "SELECT COUNT(*) FROM experiences",
        ).fetchone()[0]
        page_count = self._conn.execute(
            "SELECT COUNT(*) FROM page_fingerprints",
        ).fetchone()[0]
        bug_pattern_count = self._conn.execute(
            "SELECT COUNT(*) FROM bug_patterns",
        ).fetchone()[0]
        fix_exp_count = self._conn.execute(
            "SELECT COUNT(*) FROM fix_experiences",
        ).fetchone()[0]
        return {
            "total_tests": history_count,
            "total_experiences": experience_count,
            "known_pages": page_count,
            "bug_patterns": bug_pattern_count,
            "fix_experiences": fix_exp_count,
        }

    # ── Bug 模式（v1.3）──────────────────────────────────────

    @staticmethod
    def _bug_fingerprint(severity: str, category: str, title: str) -> str:
        """从BugReport固定字段生成指纹，规则明确，零AI成本。"""
        return f"{severity}:{category}:{title}"

    def save_bug_pattern(
        self,
        url: str,
        severity: str,
        category: str,
        title: str,
        description: str = "",
        location: str = "",
    ) -> int:
        """保存Bug模式（从BugReport字段直接提取）。

        如果同URL+同指纹已存在，更新hit_count和last_seen_at。
        """
        now = datetime.now(timezone.utc).isoformat()
        fp = self._bug_fingerprint(severity, category, title)

        existing = self._conn.execute(
            "SELECT id, hit_count FROM bug_patterns WHERE url=? AND fingerprint=?",
            (url, fp),
        ).fetchone()

        if existing:
            self._conn.execute(
                "UPDATE bug_patterns SET hit_count=?, last_seen_at=?, is_resolved=0 WHERE id=?",
                (existing["hit_count"] + 1, now, existing["id"]),
            )
            self._conn.commit()
            logger.debug("Bug模式命中 | {} | 次数={}", title[:40], existing["hit_count"] + 1)
            return existing["id"]

        cursor = self._conn.execute(
            """INSERT INTO bug_patterns
               (url, fingerprint, severity, category, title, description,
                location, hit_count, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (url, fp, severity, category, title, description, location, now, now),
        )
        self._conn.commit()
        logger.debug("Bug模式新增 | {}", title[:40])
        return cursor.lastrowid

    def get_bug_patterns(
        self,
        url: Optional[str] = None,
        unresolved_only: bool = True,
        limit: int = 20,
    ) -> list[dict]:
        """查询Bug模式。"""
        conditions = []
        params: list = []

        if url:
            conditions.append("url LIKE ?")
            params.append(f"%{url}%")
        if unresolved_only:
            conditions.append("is_resolved = 0")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM bug_patterns {where} ORDER BY hit_count DESC, last_seen_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_bug_resolved(self, url: str, severity: str, category: str, title: str) -> None:
        """标记Bug已修复。"""
        fp = self._bug_fingerprint(severity, category, title)
        self._conn.execute(
            "UPDATE bug_patterns SET is_resolved=1 WHERE url=? AND fingerprint=?",
            (url, fp),
        )
        self._conn.commit()

    # ── 修复经验（v1.3）──────────────────────────────────────

    def save_fix_experience(
        self,
        url: str,
        bug_title: str,
        bug_severity: str,
        bug_category: str = "",
        bug_description: str = "",
        fix_analysis: str = "",
        fix_patches_json: str = "[]",
        fix_confidence: float = 0.0,
        fix_risk_level: str = "medium",
        fix_verified: bool = False,
    ) -> int:
        """保存修复经验（Bug发现+修复方案的完整记忆）。"""
        now = datetime.now(timezone.utc).isoformat()
        fp = self._bug_fingerprint(bug_severity, bug_category, bug_title)

        cursor = self._conn.execute(
            """INSERT INTO fix_experiences
               (url, bug_fingerprint, bug_title, bug_severity, bug_category,
                bug_description, fix_analysis, fix_patches_json,
                fix_confidence, fix_risk_level, fix_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, fp, bug_title, bug_severity, bug_category, bug_description,
             fix_analysis, fix_patches_json, fix_confidence, fix_risk_level,
             1 if fix_verified else 0, now),
        )
        self._conn.commit()
        logger.debug("修复经验已保存 | {} | 置信度={:.0%}", bug_title[:40], fix_confidence)
        return cursor.lastrowid

    def get_fix_experiences(
        self,
        url: Optional[str] = None,
        bug_fingerprint: Optional[str] = None,
        verified_only: bool = False,
        limit: int = 10,
    ) -> list[dict]:
        """查询修复经验。"""
        conditions = []
        params: list = []

        if url:
            conditions.append("url LIKE ?")
            params.append(f"%{url}%")
        if bug_fingerprint:
            conditions.append("bug_fingerprint = ?")
            params.append(bug_fingerprint)
        if verified_only:
            conditions.append("fix_verified = 1")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._conn.execute(
            f"""SELECT * FROM fix_experiences {where}
                ORDER BY fix_verified DESC, fix_confidence DESC, created_at DESC
                LIMIT ?""",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 记忆检索（v1.3）──────────────────────────────────────

    def get_context_for_url(self, url: str, max_chars: int = 500) -> str:
        """检索某URL的全部相关记忆，压缩为注入提示词的上下文字符串。

        分层查询：
        1. 同URL的Bug模式（最多5条，按hit_count排序）
        2. 同URL的修复经验（最多3条，优先已验证的）
        3. 同URL的历史通过率趋势

        返回控制在max_chars字符以内，直接可注入提示词。
        """
        parts: list[str] = []

        # 1. Bug模式
        bugs = self.get_bug_patterns(url=url, limit=5)
        if bugs:
            bug_lines = []
            for b in bugs:
                resolved = "已修复" if b["is_resolved"] else f"出现{b['hit_count']}次"
                bug_lines.append(f"  - [{b['severity']}] {b['title']} ({resolved})")
            parts.append("已知Bug:\n" + "\n".join(bug_lines))

        # 2. 修复经验
        fixes = self.get_fix_experiences(url=url, limit=3)
        if fixes:
            fix_lines = []
            for f in fixes:
                verified = "已验证" if f["fix_verified"] else "未验证"
                fix_lines.append(f"  - {f['bug_title']}: {f['fix_analysis'][:60]} ({verified})")
            parts.append("修复经验:\n" + "\n".join(fix_lines))

        # 3. 通过率趋势
        fp = self.get_page_fingerprint(url)
        if fp and fp["test_count"] > 1:
            parts.append(
                f"历史: 测试{fp['test_count']}次, 平均通过率{fp['avg_pass_rate']:.0%}"
            )

        if not parts:
            return ""

        context = "\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars - 3] + "..."
        return context

    # ── 淘汰清理（v1.3）──────────────────────────────────────

    def cleanup(self, history_days: int = 30, max_summaries_per_url: int = 10) -> dict:
        """清理过期记忆数据。

        Args:
            history_days: 原始测试记录保留天数
            max_summaries_per_url: 同URL最多保留Bug模式条数

        Returns:
            dict: 清理统计
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=history_days)).isoformat()

        # 清理过期测试历史
        deleted_history = self._conn.execute(
            "DELETE FROM test_history WHERE created_at < ?", (cutoff,),
        ).rowcount

        # 清理同URL多余的Bug模式（保留hit_count最高的）
        deleted_bugs = 0
        urls = self._conn.execute(
            "SELECT DISTINCT url FROM bug_patterns"
        ).fetchall()
        for row in urls:
            u = row["url"]
            excess = self._conn.execute(
                """SELECT id FROM bug_patterns WHERE url=?
                   ORDER BY hit_count DESC, last_seen_at DESC
                   LIMIT -1 OFFSET ?""",
                (u, max_summaries_per_url),
            ).fetchall()
            if excess:
                ids = [r["id"] for r in excess]
                placeholders = ",".join("?" * len(ids))
                self._conn.execute(
                    f"DELETE FROM bug_patterns WHERE id IN ({placeholders})", ids,
                )
                deleted_bugs += len(ids)

        self._conn.commit()

        stats = {
            "deleted_history": deleted_history,
            "deleted_bug_patterns": deleted_bugs,
        }
        if deleted_history or deleted_bugs:
            logger.info("记忆清理完成 | {}", stats)
        return stats

    def _update_fingerprint(self, url: str, pass_rate: float) -> None:
        """更新页面指纹。"""
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_page_fingerprint(url)

        if existing:
            new_count = existing["test_count"] + 1
            # 滑动平均
            new_avg = (existing["avg_pass_rate"] * existing["test_count"] + pass_rate) / new_count
            self._conn.execute(
                """UPDATE page_fingerprints
                   SET last_tested_at=?, test_count=?, avg_pass_rate=?
                   WHERE url=?""",
                (now, new_count, new_avg, url),
            )
        else:
            self._conn.execute(
                """INSERT INTO page_fingerprints
                   (url, last_tested_at, test_count, avg_pass_rate)
                   VALUES (?, ?, 1, ?)""",
                (url, now, pass_rate),
            )
        self._conn.commit()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("记忆存储已关闭")
