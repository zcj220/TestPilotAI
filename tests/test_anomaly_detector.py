"""
通用异常检测器的单元测试。

验证：
- 异常类型和严重度枚举
- AnomalyReport 属性
- AnomalyDetector 的错误关键词和选择器配置
"""

from src.testing.anomaly_detector import (
    Anomaly, AnomalyDetector, AnomalyReport,
    AnomalySeverity, AnomalyType,
)


class TestAnomalyTypes:
    """异常类型枚举测试。"""

    def test_all_types_defined(self) -> None:
        assert AnomalyType.BLANK_PAGE == "blank_page"
        assert AnomalyType.JS_ERROR == "js_error"
        assert AnomalyType.NETWORK_ERROR == "network_error"
        assert AnomalyType.ERROR_ELEMENT == "error_element"
        assert AnomalyType.LAYOUT_OVERFLOW == "layout_overflow"

    def test_all_severities_defined(self) -> None:
        assert AnomalySeverity.CRITICAL == "critical"
        assert AnomalySeverity.HIGH == "high"
        assert AnomalySeverity.MEDIUM == "medium"
        assert AnomalySeverity.LOW == "low"


class TestAnomalyReport:
    """异常报告测试。"""

    def test_empty_report(self) -> None:
        report = AnomalyReport()
        assert not report.has_issues
        assert report.critical_count == 0

    def test_report_with_anomalies(self) -> None:
        report = AnomalyReport(anomalies=[
            Anomaly(AnomalyType.BLANK_PAGE, AnomalySeverity.CRITICAL, "白屏", "body为空"),
            Anomaly(AnomalyType.JS_ERROR, AnomalySeverity.MEDIUM, "JS错误", "undefined"),
        ])
        assert report.has_issues
        assert report.critical_count == 1
        assert len(report.anomalies) == 2

    def test_critical_count_multiple(self) -> None:
        report = AnomalyReport(anomalies=[
            Anomaly(AnomalyType.BLANK_PAGE, AnomalySeverity.CRITICAL, "a", "a"),
            Anomaly(AnomalyType.NETWORK_ERROR, AnomalySeverity.CRITICAL, "b", "b"),
            Anomaly(AnomalyType.JS_ERROR, AnomalySeverity.LOW, "c", "c"),
        ])
        assert report.critical_count == 2


class TestAnomalyDetectorConfig:
    """检测器配置测试（不需要Page对象）。"""

    def test_error_selectors_not_empty(self) -> None:
        assert len(AnomalyDetector.ERROR_SELECTORS) > 0

    def test_error_keywords_not_empty(self) -> None:
        assert len(AnomalyDetector.ERROR_KEYWORDS) > 0

    def test_error_keywords_are_lowercase(self) -> None:
        for kw in AnomalyDetector.ERROR_KEYWORDS:
            assert kw == kw.lower(), f"关键词应全小写: {kw}"
