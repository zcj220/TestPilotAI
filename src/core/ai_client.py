"""
AI 客户端模块

基于 OpenAI SDK 封装方舟平台 API 调用，使用 Doubao-Seed-1.8 统一模型。
该模型同时支持文本生成和视觉理解（图片/视频），专为 Agent 场景优化。

调用方式参考 OratorMaster 项目已验证的实现：
- 使用 OpenAI SDK（方舟 API 完全兼容 OpenAI 格式）
- base_url 指向方舟平台端点
- 支持 Chat Completions 和 Responses API
"""

import base64
from pathlib import Path
from typing import Optional

from loguru import logger
from openai import OpenAI

from src.core.config import AIConfig
from src.core.exceptions import (
    AIAuthenticationError,
    AIError,
    AIRateLimitError,
    AIResponseError,
)


class AIClient:
    """方舟平台 AI 客户端。

    封装 Doubao-Seed-1.8 模型的文本生成和视觉理解能力。
    通过 OpenAI SDK 兼容接口调用，与 OratorMaster 项目使用相同的调用模式。

    典型使用：
        client = AIClient(config)
        # 纯文本对话
        response = client.chat("请生成一个登录页面的测试用例")
        # 视觉理解（截图分析）
        response = client.analyze_screenshot("/path/to/screenshot.png", "这个页面有什么Bug？")
    """

    def __init__(self, config: Optional[AIConfig] = None) -> None:
        """初始化 AI 客户端。

        Args:
            config: AI 配置。如果不传则使用默认配置。

        Raises:
            AIAuthenticationError: API 密钥未配置
        """
        self._config = config or AIConfig()

        if not self._config.api_key:
            raise AIAuthenticationError(
                message="方舟平台 API 密钥未配置",
                detail="请在 .env 文件或环境变量中设置 TP_AI_API_KEY",
            )

        # 使用 OpenAI SDK 连接方舟平台（与 OratorMaster 相同的方式）
        self._client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.api_base_url,
            timeout=self._config.request_timeout_seconds,
            max_retries=self._config.max_retries,
        )

        logger.info(
            "AI 客户端初始化完成 | 模型={} | 思考深度={}",
            self._config.model,
            self._config.reasoning_effort,
        )

    def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """纯文本对话（测试脚本生成、Bug修复建议、报告生成等）。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（设定AI角色和行为）
            reasoning_effort: 思考深度覆盖，不传则使用默认配置

        Returns:
            str: AI 生成的文本响应

        Raises:
            AIError: API 调用失败
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return self._call_chat(messages, reasoning_effort)

    def analyze_screenshot(
        self,
        image_path: str,
        prompt: str = "请描述这个页面的内容，并指出可能存在的UI问题或Bug。",
        system_prompt: str = "",
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """分析截图（视觉理解）。

        将截图以 base64 编码发送给 Doubao-Seed-1.8 视觉理解模型，
        获取页面内容描述和 Bug 检测结果。

        Args:
            image_path: 截图文件的绝对路径
            prompt: 分析提示词
            system_prompt: 系统提示词
            reasoning_effort: 思考深度覆盖

        Returns:
            str: AI 视觉分析结果

        Raises:
            AIError: API 调用失败
            FileNotFoundError: 截图文件不存在
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"截图文件不存在: {image_path}")

        # 读取图片并编码为 base64
        image_data = path.read_bytes()
        base64_image = base64.b64encode(image_data).decode("utf-8")

        # 根据文件扩展名确定 MIME 类型
        suffix = path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(suffix, "image/png")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}",
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        })

        logger.info("发送截图分析请求 | 文件={} | 大小={}KB", path.name, len(image_data) // 1024)
        return self._call_chat(messages, reasoning_effort)

    def analyze_screenshot_url(
        self,
        image_url: str,
        prompt: str = "请描述这个页面的内容，并指出可能存在的UI问题或Bug。",
        system_prompt: str = "",
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """通过 URL 分析截图（适用于截图已上传到云存储的场景）。

        Args:
            image_url: 截图的公网或内网 URL
            prompt: 分析提示词
            system_prompt: 系统提示词
            reasoning_effort: 思考深度覆盖

        Returns:
            str: AI 视觉分析结果
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        })

        logger.info("发送截图URL分析请求 | URL={}", image_url[:80])
        return self._call_chat(messages, reasoning_effort)

    def _call_chat(
        self,
        messages: list[dict],
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """调用 Chat Completions API 的内部方法。

        Args:
            messages: 对话消息列表
            reasoning_effort: 思考深度覆盖

        Returns:
            str: AI 响应文本

        Raises:
            AIAuthenticationError: 认证失败
            AIRateLimitError: 频率超限
            AIResponseError: 响应解析失败
            AIError: 其他 API 错误
        """
        effective_reasoning = reasoning_effort or self._config.reasoning_effort

        try:
            response = self._client.chat.completions.create(
                model=self._config.model,
                messages=messages,
                max_completion_tokens=self._config.max_completion_tokens,
                reasoning_effort=effective_reasoning,
            )

            # 提取响应文本
            if not response.choices:
                raise AIResponseError(
                    message="AI 返回了空响应",
                    detail=f"response_id={response.id}",
                )

            content = response.choices[0].message.content
            if content is None:
                raise AIResponseError(
                    message="AI 响应内容为空",
                    detail=f"finish_reason={response.choices[0].finish_reason}",
                )

            # 记录 Token 使用量
            if response.usage:
                logger.debug(
                    "API 调用完成 | 输入={} tokens | 输出={} tokens | 思考深度={}",
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    effective_reasoning,
                )

            return content

        except AIError:
            raise
        except Exception as e:
            error_msg = str(e)

            # 分类处理不同的错误
            if "401" in error_msg or "authentication" in error_msg.lower():
                raise AIAuthenticationError(
                    message="API 认证失败",
                    detail="请检查 TP_AI_API_KEY 是否正确",
                )
            elif "429" in error_msg or "rate" in error_msg.lower():
                raise AIRateLimitError(
                    message="API 调用频率超限",
                    detail="请稍后重试，或降低调用频率",
                )
            else:
                raise AIError(
                    message="AI API 调用失败",
                    detail=error_msg,
                )
