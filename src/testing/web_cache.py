"""
Web 页面缓存模块（v14.7）

缓存 ARIA Snapshot 降级的选择器映射，避免重复分析。
持久化到 testpilot/.web_cache.json，跨运行复用。

缓存结构：
  页面URL → DOM指纹 → {
    aria_fallbacks: { CSS选择器 → {role, name, hit_count} },
    ai_coords: { CSS选择器 → [x, y] }
  }
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


class ARIAFallback:
    """单个 ARIA 降级选择器的缓存条目。"""

    def __init__(self, role: str, name: str, hit_count: int = 0):
        self.role = role
        self.name = name
        self.hit_count = hit_count

    def to_dict(self) -> dict:
        return {"role": self.role, "name": self.name, "hit_count": self.hit_count}

    @classmethod
    def from_dict(cls, d: dict) -> "ARIAFallback":
        return cls(role=d.get("role", ""), name=d.get("name", ""), hit_count=d.get("hit_count", 0))


class WebPageCache:
    """Web 页面缓存管理器。

    缓存层级：
    - ARIA fallbacks：CSS选择器失败时的 getByRole 替代方案
    - AI coords：AI 截图分析的归一化坐标（最后兜底）
    """

    def __init__(self):
        self._cache_path: Optional[Path] = None
        # { page_url: { "dom_hash": str, "aria": {sel: ARIAFallback}, "coords": {sel: (x,y)} } }
        self._pages: dict[str, dict] = {}

    def init(self, blueprint_source_path: Optional[Path], app_name: str = "") -> None:
        """根据蓝本路径初始化缓存文件位置并加载。"""
        self._app_name = app_name
        if blueprint_source_path:
            cache_dir = blueprint_source_path.parent
        else:
            cache_dir = None

        if cache_dir and cache_dir.exists():
            self._cache_path = cache_dir / ".web_cache.json"
            self._load()
        else:
            self._cache_path = None

    def _load(self) -> None:
        """从磁盘加载缓存。"""
        if not self._cache_path or not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                return
            if data.get("app_name") != self._app_name:
                logger.info("Web缓存app_name不匹配，已忽略")
                return
            for url, entry in data.get("pages", {}).items():
                aria = {}
                for sel, fb in entry.get("aria_fallbacks", {}).items():
                    aria[sel] = ARIAFallback.from_dict(fb)
                coords = {}
                for sel, xy in entry.get("ai_coords", {}).items():
                    coords[sel] = tuple(xy)
                self._pages[url] = {
                    "dom_hash": entry.get("dom_hash", ""),
                    "aria": aria,
                    "coords": coords,
                }
            if self._pages:
                logger.info("📦 Web缓存已加载 | {} 个页面 | 来源: {}", len(self._pages), self._cache_path.name)
        except Exception as e:
            logger.debug("Web缓存加载失败（非致命）: {}", str(e)[:100])

    def save(self) -> None:
        """将缓存持久化到磁盘。"""
        if not self._cache_path or not self._pages:
            return
        try:
            pages = {}
            for url, entry in self._pages.items():
                pages[url] = {
                    "dom_hash": entry.get("dom_hash", ""),
                    "aria_fallbacks": {s: fb.to_dict() for s, fb in entry.get("aria", {}).items()},
                    "ai_coords": {s: list(v) for s, v in entry.get("coords", {}).items()},
                }
            data = {
                "schema_version": 1,
                "app_name": self._app_name,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "pages": pages,
            }
            self._cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug("Web缓存已保存 | {} 个页面 → {}", len(pages), self._cache_path.name)
        except Exception as e:
            logger.debug("Web缓存保存失败（非致命）: {}", str(e)[:100])

    # ── 查询接口 ──

    def get_aria_fallback(self, page_url: str, selector: str) -> Optional[ARIAFallback]:
        """查询某个 CSS 选择器的 ARIA 降级缓存。"""
        entry = self._pages.get(page_url)
        if not entry:
            return None
        return entry.get("aria", {}).get(selector)

    def get_ai_coord(self, page_url: str, selector: str) -> Optional[tuple[float, float]]:
        """查询某个选择器的 AI 坐标缓存。"""
        entry = self._pages.get(page_url)
        if not entry:
            return None
        return entry.get("coords", {}).get(selector)

    # ── 更新接口 ──

    def set_aria_fallback(self, page_url: str, selector: str, role: str, name: str) -> None:
        """记录一个成功的 ARIA 降级选择器。"""
        if page_url not in self._pages:
            self._pages[page_url] = {"dom_hash": "", "aria": {}, "coords": {}}
        entry = self._pages[page_url]
        existing = entry["aria"].get(selector)
        if existing and existing.role == role and existing.name == name:
            existing.hit_count += 1
        else:
            entry["aria"][selector] = ARIAFallback(role=role, name=name, hit_count=1)
        logger.debug("  ARIA缓存写入: {} → getByRole('{}', name='{}')", selector, role, name)

    def set_ai_coord(self, page_url: str, selector: str, x: float, y: float) -> None:
        """记录一个 AI 分析的归一化坐标。"""
        if page_url not in self._pages:
            self._pages[page_url] = {"dom_hash": "", "aria": {}, "coords": {}}
        self._pages[page_url]["coords"][selector] = (x, y)

    def invalidate_ai_coord(self, page_url: str, selector: str) -> None:
        """使某个 AI 坐标缓存条目失效（点击后 DOM 无变化时调用）。"""
        entry = self._pages.get(page_url)
        if entry and selector in entry.get("coords", {}):
            del entry["coords"][selector]
            logger.debug("  AI坐标缓存失效: {}", selector)

    def update_dom_hash(self, page_url: str, dom_hash: str) -> bool:
        """更新页面 DOM 指纹。返回 True 表示页面已变化（缓存需刷新）。"""
        entry = self._pages.get(page_url)
        if not entry:
            self._pages[page_url] = {"dom_hash": dom_hash, "aria": {}, "coords": {}}
            return True
        if entry["dom_hash"] != dom_hash:
            # 页面变了，清空旧的 AI 坐标缓存（ARIA 缓存保留，因为 role/name 通常不变）
            entry["dom_hash"] = dom_hash
            entry["coords"] = {}
            logger.info("  页面DOM已变化({}), AI坐标缓存已清空, ARIA缓存保留", page_url)
            return True
        return False

    @staticmethod
    def compute_dom_hash(dom_ctx_json: str) -> str:
        """从 DOM 上下文 JSON 计算指纹 hash。"""
        return hashlib.md5(dom_ctx_json.encode()).hexdigest()[:8]
