"""
测试报告分析与可视化数据生成（v5.2）

从历史测试数据中提取可视化所需的聚合数据：
1. 通过率趋势（折线图数据）
2. 截图时间线（按步骤顺序）
3. Bug热力图（页面/元素维度）
4. 历史对比（两次报告diff）
5. HTML报告导出

数据源：MemoryStore 中的 test_history 表
"""

import json
from collections import Counter
from datetime import datetime
from typing import Optional

from loguru import logger


class ReportAnalytics:
    """测试报告分析引擎。"""

    def __init__(self, memory_store) -> None:
        self._store = memory_store

    # ── 通过率趋势 ──

    def get_pass_rate_trend(self, url: Optional[str] = None, limit: int = 50) -> dict:
        """获取通过率趋势数据（折线图）。"""
        history = self._store.get_history(url=url, limit=limit)
        history.reverse()

        labels, pass_rates, total_steps = [], [], []
        bug_counts, durations, test_names = [], [], []

        for r in history:
            created = r.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created)
                labels.append(dt.strftime("%m-%d %H:%M"))
            except (ValueError, TypeError):
                labels.append(created[:16] if created else "unknown")

            pass_rates.append(round(r.get("pass_rate", 0.0), 4))
            total_steps.append(r.get("total_steps", 0))
            bug_counts.append(r.get("bug_count", 0))
            durations.append(round(r.get("duration_seconds", 0.0), 1))
            test_names.append(r.get("test_name", ""))

        return {
            "labels": labels, "pass_rates": pass_rates,
            "total_steps": total_steps, "bug_counts": bug_counts,
            "durations": durations, "test_names": test_names,
            "count": len(history),
        }

    # ── 截图时间线 ──

    def get_screenshot_timeline(self, test_id: int) -> dict:
        """获取单次测试的截图时间线。"""
        row = self._store._conn.execute(
            "SELECT * FROM test_history WHERE id = ?", (test_id,)
        ).fetchone()
        if not row:
            return {"test_name": "", "steps": [], "error": "记录不存在"}

        record = dict(row)
        steps_data = []
        try:
            for s in json.loads(record.get("steps_json", "[]")):
                steps_data.append({
                    "step": s.get("step", 0),
                    "action": s.get("action", ""),
                    "status": s.get("status", ""),
                    "description": s.get("description", ""),
                    "screenshot_path": s.get("screenshot_path", ""),
                    "error": s.get("error"),
                })
        except json.JSONDecodeError:
            pass

        return {
            "test_name": record.get("test_name", ""),
            "url": record.get("url", ""),
            "pass_rate": record.get("pass_rate", 0.0),
            "created_at": record.get("created_at", ""),
            "steps": steps_data,
        }

    # ── Bug热力图 ──

    def get_bug_heatmap(self, url: Optional[str] = None, limit: int = 100) -> dict:
        """生成Bug热力图数据。"""
        history = self._store.get_history(url=url, limit=limit)

        page_bugs = Counter()
        category_bugs = Counter()
        severity_bugs = Counter()
        location_bugs = Counter()
        total_bugs = 0

        for record in history:
            test_url = record.get("url", "unknown")
            try:
                bugs_raw = json.loads(record.get("bugs_json", "[]"))
            except json.JSONDecodeError:
                continue
            for bug in bugs_raw:
                total_bugs += 1
                page_bugs[test_url] += 1
                category_bugs[bug.get("category", "未分类")] += 1
                severity_bugs[bug.get("severity", "unknown")] += 1
                loc = bug.get("location", "").strip()
                if loc:
                    location_bugs[loc] += 1

        return {
            "by_page": [{"url": k, "count": v} for k, v in page_bugs.most_common(20)],
            "by_category": [{"category": k, "count": v} for k, v in category_bugs.most_common(20)],
            "by_severity": dict(severity_bugs),
            "by_location": [{"location": k, "count": v} for k, v in location_bugs.most_common(20)],
            "total_bugs": total_bugs,
        }

    # ── 历史对比 ──

    def compare_reports(self, test_id_a: int, test_id_b: int) -> dict:
        """对比两次测试报告。"""
        conn = self._store._conn
        row_a = conn.execute("SELECT * FROM test_history WHERE id = ?", (test_id_a,)).fetchone()
        row_b = conn.execute("SELECT * FROM test_history WHERE id = ?", (test_id_b,)).fetchone()
        if not row_a or not row_b:
            return {"error": "记录不存在", "summary": {}, "new_bugs": [], "fixed_bugs": [], "persistent_bugs": []}

        a, b = dict(row_a), dict(row_b)
        summary = {
            "test_a": {"id": test_id_a, "name": a.get("test_name", ""), "created_at": a.get("created_at", "")},
            "test_b": {"id": test_id_b, "name": b.get("test_name", ""), "created_at": b.get("created_at", "")},
            "pass_rate_a": a.get("pass_rate", 0),
            "pass_rate_b": b.get("pass_rate", 0),
            "pass_rate_change": round(b.get("pass_rate", 0) - a.get("pass_rate", 0), 4),
            "bug_count_a": a.get("bug_count", 0),
            "bug_count_b": b.get("bug_count", 0),
            "bug_count_change": b.get("bug_count", 0) - a.get("bug_count", 0),
            "duration_a": a.get("duration_seconds", 0),
            "duration_b": b.get("duration_seconds", 0),
        }

        bugs_a = self._parse_bugs(a.get("bugs_json", "[]"))
        bugs_b = self._parse_bugs(b.get("bugs_json", "[]"))
        titles_a = {bg["title"] for bg in bugs_a}
        titles_b = {bg["title"] for bg in bugs_b}

        return {
            "summary": summary,
            "new_bugs": [bg for bg in bugs_b if bg["title"] not in titles_a],
            "fixed_bugs": [bg for bg in bugs_a if bg["title"] not in titles_b],
            "persistent_bugs": [bg for bg in bugs_b if bg["title"] in titles_a],
            "improved": summary["pass_rate_change"] > 0,
        }

    # ── HTML报告导出 ──

    def export_html_report(self, test_id: int) -> str:
        """生成独立HTML可视化报告（可直接保存为.html独立打开）。"""
        row = self._store._conn.execute(
            "SELECT * FROM test_history WHERE id = ?", (test_id,)
        ).fetchone()
        if not row:
            return "<html><body><h1>报告不存在</h1></body></html>"

        r = dict(row)
        steps = self._parse_steps(r.get("steps_json", "[]"))
        bugs = self._parse_bugs(r.get("bugs_json", "[]"))
        pr = r.get("pass_rate", 0)
        pct = f"{pr * 100:.1f}"
        rc = "#22c55e" if pr >= 0.8 else "#f59e0b" if pr >= 0.5 else "#ef4444"

        steps_html = self._render_steps_html(steps)
        bugs_html = self._render_bugs_html(bugs)
        stats_html = self._render_stats_html(r, rc, pct)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TestPilot AI - {r.get("test_name","")}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f3f4f6;color:#1f2937;padding:20px}}
.c{{max-width:900px;margin:0 auto}}
.hd{{background:linear-gradient(135deg,#3b82f6,#8b5cf6);color:#fff;padding:30px;border-radius:12px;margin-bottom:20px}}
.hd h1{{font-size:24px;margin-bottom:8px}}.hd .m{{opacity:.9;font-size:14px}}
.cd{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.cd h2{{font-size:18px;margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid #e5e7eb}}
.st{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.s{{background:#fff;border-radius:12px;padding:16px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.s .v{{font-size:28px;font-weight:700}}.s .l{{font-size:13px;color:#6b7280;margin-top:4px}}
.ft{{text-align:center;color:#9ca3af;font-size:12px;padding:20px}}
</style>
</head>
<body><div class="c">
<div class="hd"><h1>{r.get("test_name","测试报告")}</h1>
<div class="m">URL: {r.get("url","")} | {r.get("created_at","")[:19]} | 耗时: {r.get("duration_seconds",0):.1f}s</div></div>
{stats_html}
<div class="cd"><h2>测试步骤</h2>{steps_html}</div>
<div class="cd"><h2>Bug列表 ({len(bugs)})</h2>{bugs_html}</div>
<div class="ft">TestPilot AI v5.2 | 自动生成</div>
</div></body></html>"""

    # ── 内部工具方法 ──

    @staticmethod
    def _parse_bugs(bugs_json: str) -> list[dict]:
        try:
            return json.loads(bugs_json)
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _parse_steps(steps_json: str) -> list[dict]:
        try:
            return json.loads(steps_json)
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _render_steps_html(steps: list[dict]) -> str:
        html = ""
        for s in steps:
            st = s.get("status", "")
            icon = {"passed": "&#10004;", "failed": "&#10008;", "error": "&#9888;"}.get(st, "&#8226;")
            color = {"passed": "#22c55e", "failed": "#ef4444", "error": "#f59e0b"}.get(st, "#6b7280")
            err = s.get("error", "")
            err_html = f'<div style="color:#ef4444;font-size:13px;margin-top:4px">{err}</div>' if err else ""
            html += (
                f'<div style="display:flex;align-items:flex-start;padding:10px 12px;'
                f'border-left:3px solid {color};margin-bottom:8px;background:#f9fafb;border-radius:0 6px 6px 0">'
                f'<span style="font-size:18px;margin-right:10px;color:{color}">{icon}</span>'
                f'<div style="flex:1"><div style="font-weight:600;font-size:14px">'
                f'Step {s.get("step",0)}: {s.get("action","")}</div>'
                f'<div style="color:#6b7280;font-size:13px">{s.get("description","")}</div>'
                f'{err_html}</div></div>'
            )
        return html or '<div style="color:#6b7280;padding:20px;text-align:center">无步骤数据</div>'

    @staticmethod
    def _render_bugs_html(bugs: list[dict]) -> str:
        if not bugs:
            return '<div style="color:#22c55e;padding:20px;text-align:center">未发现Bug</div>'
        html = ""
        for b in bugs:
            sev = b.get("severity", "unknown")
            sc = {"critical": "#dc2626", "major": "#ea580c", "minor": "#ca8a04"}.get(sev, "#6b7280")
            html += (
                f'<div style="padding:12px;border:1px solid #e5e7eb;border-radius:8px;margin-bottom:8px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="background:{sc};color:#fff;padding:2px 8px;border-radius:4px;'
                f'font-size:12px;font-weight:600">{sev.upper()}</span>'
                f'<span style="font-weight:600;font-size:14px">{b.get("title","")}</span></div>'
                f'<div style="color:#6b7280;font-size:13px">{b.get("description","")}</div></div>'
            )
        return html

    @staticmethod
    def _render_stats_html(r: dict, rate_color: str, pct: str) -> str:
        return (
            f'<div class="st">'
            f'<div class="s"><div class="v" style="color:{rate_color}">{pct}%</div><div class="l">通过率</div></div>'
            f'<div class="s"><div class="v">{r.get("passed_steps",0)}/{r.get("total_steps",0)}</div><div class="l">通过/总步骤</div></div>'
            f'<div class="s"><div class="v" style="color:#ef4444">{r.get("bug_count",0)}</div><div class="l">Bug数量</div></div>'
            f'<div class="s"><div class="v">{r.get("duration_seconds",0):.1f}s</div><div class="l">耗时</div></div>'
            f'</div>'
        )
