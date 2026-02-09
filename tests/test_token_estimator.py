"""Tests for token estimator."""

from conductor.tokens.estimator import TokenEstimator


class TestTokenEstimator:
    def test_initial_usage_zero(self):
        est = TokenEstimator()
        usage = est.get_usage()
        assert usage["used"] == 0
        assert usage["percentage"] == 0

    def test_count_responses(self):
        est = TokenEstimator()
        est.on_claude_response("session-1")
        est.on_claude_response("session-1")
        est.on_claude_response("session-2")

        usage1 = est.get_usage("session-1")
        assert usage1["used"] == 2

        usage2 = est.get_usage("session-2")
        assert usage2["used"] == 1

        total = est.get_usage()
        assert total["used"] == 3

    def test_percentage_calculation(self):
        est = TokenEstimator()
        for _ in range(36):
            est.on_claude_response("s1")
        usage = est.get_usage("s1")
        assert usage["percentage"] == 80  # 36/45 = 80%

    def test_threshold_warning(self):
        est = TokenEstimator()
        for _ in range(36):
            est.on_claude_response("s1")
        assert est.check_thresholds() == "warning"

    def test_threshold_danger(self):
        est = TokenEstimator()
        for _ in range(41):
            est.on_claude_response("s1")
        assert est.check_thresholds() == "danger"

    def test_threshold_critical(self):
        est = TokenEstimator()
        for _ in range(43):
            est.on_claude_response("s1")
        assert est.check_thresholds() == "critical"

    def test_no_threshold(self):
        est = TokenEstimator()
        for _ in range(10):
            est.on_claude_response("s1")
        assert est.check_thresholds() is None

    def test_max_5x_tier(self):
        est = TokenEstimator()
        est.tier = "max_5x"
        usage = est.get_usage()
        assert usage["limit"] == 225

    def test_reset_window(self):
        est = TokenEstimator()
        est.on_claude_response("s1")
        est.reset_window()
        assert est.get_usage()["used"] == 0
