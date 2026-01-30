import os
import pytest
from server.evaluators.metrics import (
    evaluate_metric,
    evaluate_url_match,
    evaluate_file_exists,
    evaluate_app_launched,
    evaluate_text_present,
    evaluate_process_running,
)


class TestUrlMatchMetric:
    def test_evaluate_url_match_exact(self):
        result = evaluate_url_match("expected_url", tolerance="exact")
        assert isinstance(result, bool)

    def test_evaluate_url_match_contains(self):
        result = evaluate_url_match("github", tolerance="contains")
        assert isinstance(result, bool)

    def test_evaluate_url_match_regex(self):
        result = evaluate_url_match(r"github\.com", tolerance="regex")
        assert isinstance(result, bool)


class TestFileExistsMetric:
    def test_evaluate_file_exists_true(self):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = evaluate_file_exists(temp_path)
            assert result is True
        finally:
            os.unlink(temp_path)

    def test_evaluate_file_exists_false(self):
        result = evaluate_file_exists("/nonexistent/path/file.txt")
        assert result is False

    def test_evaluate_file_exists_with_content(self):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("Hello World")
            temp_path = f.name

        try:
            result = evaluate_file_exists(temp_path, must_contain="Hello")
            assert result is True
            result = evaluate_file_exists(temp_path, must_contain="Goodbye")
            assert result is False
        finally:
            os.unlink(temp_path)


class TestAppLaunchedMetric:
    def test_evaluate_app_launched_nonexistent(self):
        result = evaluate_app_launched("nonexistent_app_xyz")
        assert result is False

    def test_evaluate_app_launched_common(self):
        result = evaluate_app_launched("bash")
        assert isinstance(result, bool)


class TestTextPresentMetric:
    def test_evaluate_text_present_screen(self):
        result = evaluate_text_present("test", location="screen")
        assert isinstance(result, bool)

    def test_evaluate_text_present_clipboard(self):
        result = evaluate_text_present("test", location="clipboard")
        assert isinstance(result, bool)

    def test_evaluate_text_present_terminal(self):
        result = evaluate_text_present("test", location="terminal")
        assert isinstance(result, bool)


class TestProcessRunningMetric:
    def test_evaluate_process_running_nonexistent(self):
        result = evaluate_process_running("nonexistent_proc_12345")
        assert result is False


class TestMetricRegistry:
    def test_evaluate_metric_url_match(self):
        result = evaluate_metric("url_match", expected_url="test", tolerance="exact")
        assert isinstance(result, bool)

    def test_evaluate_metric_file_exists(self):
        result = evaluate_metric("file_exists", filepath="/nonexistent")
        assert result is False

    def test_evaluate_metric_unknown(self):
        with pytest.raises(ValueError, match="Unknown metric type"):
            evaluate_metric("unknown_metric")

    def test_list_metrics(self):
        from server.evaluators.metrics import list_metrics

        metrics = list_metrics()
        assert "url_match" in metrics
        assert "file_exists" in metrics
        assert "app_launched" in metrics
        assert "text_present" in metrics
        assert "process_running" in metrics
