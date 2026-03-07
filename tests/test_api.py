"""
API 路由的单元测试。

使用 FastAPI 的 TestClient 进行集成测试，
验证端点响应格式和状态码。
"""

import pytest
from fastapi.testclient import TestClient

from src.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """创建测试客户端。"""
    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    """健康检查端点测试。"""

    def test_health_returns_200(self, client: TestClient) -> None:
        """健康检查应该返回 200。"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_format(self, client: TestClient) -> None:
        """健康检查响应应包含所有必需字段。"""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "sandbox_count" in data
        assert "browser_ready" in data

    def test_health_version_matches(self, client: TestClient) -> None:
        """版本号应该与包版本一致。"""
        from src import __version__
        response = client.get("/api/v1/health")
        assert response.json()["version"] == __version__


class TestSandboxEndpoints:
    """沙箱 API 端点测试。"""

    def test_list_sandboxes_empty(self, client: TestClient) -> None:
        """初始状态应该没有活跃沙箱。"""
        response = client.get("/api/v1/sandbox")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_sandbox_invalid_path(self, client: TestClient) -> None:
        """传入不存在的路径应该返回 400 或 500。"""
        response = client.post(
            "/api/v1/sandbox/create",
            json={"project_path": "C:/nonexistent/path/12345"},
        )
        assert response.status_code in (400, 500)

    def test_get_sandbox_status_not_found(self, client: TestClient) -> None:
        """查询不存在的沙箱应该返回 404。"""
        response = client.get("/api/v1/sandbox/nonexistent-id/status")
        assert response.status_code == 404


class TestBrowserEndpoints:
    """浏览器 API 端点测试。"""

    def test_navigate_without_launch(self, client: TestClient) -> None:
        """未启动浏览器时导航应该返回 500。"""
        response = client.post(
            "/api/v1/browser/navigate",
            json={"url": "https://example.com"},
        )
        assert response.status_code == 500

    def test_click_without_launch(self, client: TestClient) -> None:
        """未启动浏览器时点击应该返回 500。"""
        response = client.post(
            "/api/v1/browser/click",
            json={"selector": "#test"},
        )
        assert response.status_code == 500

    def test_close_browser_safe(self, client: TestClient) -> None:
        """关闭未启动的浏览器应该安全返回。"""
        response = client.post("/api/v1/browser/close")
        assert response.status_code == 200
