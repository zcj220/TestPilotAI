"""
蓝本自动生成器（v10.1）

核心流程：
1. 用 Playwright 访问目标 URL，提取 HTML 结构和可交互元素
2. 截图当前页面
3. HTML + 截图 + 元素信息 → AI 生成完整 testpilot.json
4. 解析并验证蓝本 → 保存到指定路径

支持：
- 给一个 URL 自动生成蓝本（全自动）
- 给 HTML 片段 + 描述生成蓝本（无需浏览器）
- 多页面应用自动发现链接并逐页生成
"""

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Optional

from loguru import logger

from src.browser.automator import BrowserAutomator, BrowserConfig
from src.core.ai_client import AIClient
from src.core.prompts import SYSTEM_BLUEPRINT_GENERATOR
from src.testing.blueprint import Blueprint, BlueprintParser


# ── 自动生成专用提示词 ─────────────────────────────────

PROMPT_AUTO_GENERATE = """请为以下应用自动生成完整的测试蓝本（testpilot.json）。

## 应用信息
- 应用名称：{app_name}
- 应用URL：{base_url}
- 应用描述：{description}

## 页面可交互元素（自动提取）
{elements_summary}

## 页面关键文本/数据
{texts_summary}

## 页面HTML结构（精简）
```html
{html_body}
```

请严格按照蓝本 JSON Schema 生成，覆盖所有功能，每个功能独立场景。
只返回JSON，不要返回其他任何文字。"""


# ── 页面信息提取 JS ────────────────────────────────────

# 提取页面结构：可交互元素 + 文本节点 + 表格 + 导航等
EXTRACT_PAGE_INFO_JS = """() => {
    const info = { elements: [], texts: [], links: [], title: document.title };

    const seen = new Set();

    // 提取可交互元素
    const interactives = document.querySelectorAll(
        'button, [role="button"], [type="submit"], [type="button"], ' +
        'input:not([type="hidden"]), textarea, select, ' +
        'a[href], [onclick], [data-testid], [role="tab"], [role="link"]'
    );

    interactives.forEach(el => {
        if (!el.offsetParent && el.style.display !== 'contents'
            && getComputedStyle(el).display === 'none') return;

        const id = el.id ? '#' + el.id : '';
        const name = el.getAttribute('name') || '';
        const cls = (typeof el.className === 'string' && el.className.trim())
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.')
            : '';
        const testId = el.getAttribute('data-testid')
            ? `[data-testid="${el.getAttribute('data-testid')}"]` : '';
        const placeholder = el.getAttribute('placeholder') || '';
        const tag = el.tagName.toLowerCase();
        const type = el.getAttribute('type') || '';
        const text = (el.textContent || '').trim().substring(0, 60);
        const href = el.getAttribute('href') || '';
        const role = el.getAttribute('role') || '';

        // 选择最佳选择器（优先级：id > data-testid > name > class）
        const selector = id || testId
            || (name ? `${tag}[name="${name}"]` : '')
            || cls || tag;

        const key = selector + '|' + text;
        if (seen.has(key)) return;
        seen.add(key);

        info.elements.push({
            tag, type, selector, text, placeholder,
            href, role, id, name,
            hasOptions: tag === 'select'
                ? Array.from(el.options || []).map(o => ({
                    value: o.value, text: o.textContent.trim()
                })).slice(0, 10)
                : null,
        });
    });

    // 提取关键文本节点（统计数字、标题等）
    document.querySelectorAll(
        'h1, h2, h3, [class*="title"], [class*="stat"], ' +
        '[class*="total"], [class*="count"], [class*="price"], ' +
        '[class*="amount"], [id*="total"], [id*="count"], [id*="price"]'
    ).forEach(el => {
        if (!el.offsetParent) return;
        const text = (el.textContent || '').trim().substring(0, 100);
        if (!text) return;
        const id = el.id ? '#' + el.id : '';
        const cls = (typeof el.className === 'string' && el.className.trim())
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.')
            : '';
        info.texts.push({
            selector: id || cls || el.tagName.toLowerCase(),
            text,
        });
    });

    // 提取导航链接（发现多页面）
    document.querySelectorAll('a[href], [role="tab"]').forEach(el => {
        const href = el.getAttribute('href') || '';
        if (!href || href === '#' || href.startsWith('javascript:')
            || href.startsWith('mailto:') || href.startsWith('tel:')) return;
        const text = (el.textContent || '').trim().substring(0, 40);
        if (!text) return;
        info.links.push({ href, text });
    });

    return info;
}"""


class BlueprintGenerator:
    """蓝本自动生成器。

    典型使用：
        gen = BlueprintGenerator(ai_client)
        blueprint = await gen.from_url("http://localhost:3000")
        gen.save(blueprint, "shop-demo/testpilot.json")
    """

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
    ) -> None:
        self._ai = ai_client

    # ── 主入口：从 URL 自动生成 ─────────────────────────

    async def from_url(
        self,
        url: str,
        app_name: str = "",
        description: str = "",
        output_path: Optional[str] = None,
    ) -> Blueprint:
        """访问 URL，提取页面信息，AI 生成蓝本。

        Args:
            url: 目标应用 URL
            app_name: 应用名称（空则自动从页面标题提取）
            description: 应用描述（帮助 AI 理解上下文）
            output_path: 保存路径（空则不保存）

        Returns:
            Blueprint 对象
        """
        logger.info("蓝本自动生成 | URL={}", url)

        config = BrowserConfig(headless=True)
        async with BrowserAutomator(config) as browser:
            # 1. 访问页面
            await browser.navigate(url)
            await asyncio.sleep(1.5)  # 等待页面渲染稳定

            # 2. 提取页面信息
            page_info = await self._extract_page_info(browser)

            # 3. 截图（仅用于调试记录，不发给AI以避免大图超时）
            await self._take_screenshot_b64(browser)  # 保留截图到本地即可
            screenshot_b64 = ""  # 不附加截图，使用纯文字模式更稳定

            # 4. 获取精简 HTML
            html_body = await self._get_clean_html(browser)

        # 5. 自动推断 app_name
        if not app_name:
            app_name = page_info.get("title", "") or "未命名应用"

        # 6. AI 生成蓝本 JSON
        blueprint = await self._ai_generate(
            url=url,
            app_name=app_name,
            description=description,
            page_info=page_info,
            html_body=html_body,
            screenshot_b64=screenshot_b64,
        )

        # 7. 保存
        if output_path:
            self.save(blueprint, output_path)

        return blueprint

    # ── 从 HTML 片段生成（不需要浏览器）─────────────────

    async def from_html(
        self,
        html_content: str,
        base_url: str = "http://localhost:3000",
        app_name: str = "未命名应用",
    ) -> Blueprint:
        """从 HTML 字符串生成蓝本（不启动浏览器）。"""
        blueprint = await self._ai_generate(
            url=base_url,
            app_name=app_name,
            description="",
            page_info={"elements": [], "texts": [], "links": []},
            html_body=html_content[:15000],
            screenshot_b64="",
        )
        return blueprint

    # ── 保存蓝本 ─────────────────────────────────────

    @staticmethod
    def save(blueprint: Blueprint, path: str) -> Path:
        """保存蓝本到文件。"""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = blueprint.model_dump(exclude_none=True)
        out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("蓝本已保存: {} | 场景={} 步骤={}",
                     out, blueprint.total_scenarios, blueprint.total_steps)
        return out

    # ── 内部方法 ─────────────────────────────────────

    async def _extract_page_info(self, browser: BrowserAutomator) -> dict:
        """用 JS 提取页面可交互元素、文本、链接等。"""
        try:
            info = await browser.page.evaluate(EXTRACT_PAGE_INFO_JS)
            logger.info("页面信息提取完成 | 元素={} 文本={} 链接={}",
                         len(info.get("elements", [])),
                         len(info.get("texts", [])),
                         len(info.get("links", [])))
            return info
        except Exception as e:
            logger.warning("页面信息提取失败: {}", str(e)[:100])
            return {"elements": [], "texts": [], "links": [], "title": ""}

    async def _take_screenshot_b64(self, browser: BrowserAutomator) -> str:
        """截图并返回 base64 字符串。"""
        try:
            path = await browser.screenshot("blueprint_gen", full_page=True)
            data = Path(path).read_bytes()
            return base64.b64encode(data).decode("ascii")
        except Exception as e:
            logger.warning("截图失败: {}", str(e)[:80])
            return ""

    async def _get_clean_html(self, browser: BrowserAutomator) -> str:
        """获取精简 HTML（去掉 script/style/svg，限制长度）。"""
        try:
            html = await browser.page.evaluate("""() => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, svg, noscript, iframe')
                    .forEach(el => el.remove());
                return clone.innerHTML;
            }""")
            # 压缩空白
            html = re.sub(r'\s+', ' ', html or "")
            return html[:12000]
        except Exception:
            return ""

    async def _ai_generate(
        self,
        url: str,
        app_name: str,
        description: str,
        page_info: dict,
        html_body: str,
        screenshot_b64: str,
    ) -> Blueprint:
        """调用 AI 生成蓝本 JSON 并解析。"""
        if not self._ai:
            raise RuntimeError("需要 AIClient 才能生成蓝本")

        # 构造元素摘要
        elements_summary = self._format_elements(page_info.get("elements", []))
        texts_summary = self._format_texts(page_info.get("texts", []))

        user_prompt = PROMPT_AUTO_GENERATE.format(
            app_name=app_name,
            base_url=url,
            description=description or "（未提供描述，请根据页面内容推断）",
            elements_summary=elements_summary,
            texts_summary=texts_summary,
            html_body=html_body[:8000] if html_body else "（未提供）",
        )

        # 调用 AI（纯文字模式：HTML+元素信息已足够生成蓝本，不发截图避免超时）
        logger.info("AI 蓝本生成中... | app={} | url={}", app_name, url)
        raw = await asyncio.to_thread(
            self._ai.chat,
            user_prompt, SYSTEM_BLUEPRINT_GENERATOR,
        )

        # 解析 AI 返回的 JSON
        blueprint = self._parse_ai_response(raw, url, app_name)
        logger.info("蓝本生成完成 | 场景={} 步骤={}",
                     blueprint.total_scenarios, blueprint.total_steps)
        return blueprint

    def _format_elements(self, elements: list[dict]) -> str:
        """将元素列表格式化为可读摘要。"""
        if not elements:
            return "（无可交互元素）"
        lines = []
        for e in elements[:40]:
            tag = e.get("tag", "?")
            sel = e.get("selector", "?")
            text = e.get("text", "")
            ph = e.get("placeholder", "")
            etype = e.get("type", "")
            desc = text or ph or etype
            opts = e.get("hasOptions")
            opt_str = ""
            if opts:
                opt_str = " 选项:" + ",".join(
                    o.get("text", o.get("value", ""))
                    for o in opts[:5]
                )
            lines.append(f"- [{tag}] {sel} {desc}{opt_str}")
        return "\n".join(lines)

    def _format_texts(self, texts: list[dict]) -> str:
        """将文本节点格式化为摘要。"""
        if not texts:
            return "（无关键文本）"
        lines = []
        for t in texts[:20]:
            lines.append(f"- {t.get('selector','?')}: {t.get('text','')}")
        return "\n".join(lines)

    def _parse_ai_response(
        self, raw: str, url: str, app_name: str
    ) -> Blueprint:
        """从 AI 返回的文本中提取 JSON 并解析为 Blueprint。"""
        # 尝试提取 JSON 块
        json_str = self._extract_json(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("AI 返回的 JSON 解析失败: {}", str(e)[:100])
            logger.debug("原始返回前500字: {}", raw[:500])
            # 兜底：返回空蓝本
            return Blueprint(app_name=app_name, base_url=url)

        # 确保基础字段存在
        data.setdefault("app_name", app_name)
        data.setdefault("base_url", url)
        data.setdefault("version", "1.0")

        try:
            return Blueprint(**data)
        except Exception as e:
            logger.error("Blueprint 构建失败: {}", str(e)[:200])
            return Blueprint(app_name=app_name, base_url=url)

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 AI 回复中提取 JSON 字符串（支持 ```json 包裹）。"""
        # 先尝试找 ```json ... ```
        m = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 再尝试找 ``` ... ```
        m = re.search(r"```\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 尝试找最外层的 { ... }
        start = text.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
        return text.strip()
