"""Per-target names and the per-platform status line, as the webapp shows them."""

from typing import Any

import pytest

from minitest_cli.commands.target_summary import platform_lines
from minitest_cli.models.batch import BatchTargetView
from minitest_cli.models.target_labels import target_display_label


def _target(**fields: Any) -> BatchTargetView:
    return BatchTargetView.model_validate({"id": "t", "label": "iOS", "platform": "ios", **fields})


class TestTargetLabel:
    @pytest.mark.parametrize(
        "fields,label",
        [
            ({"backend": "cloud", "osVersion": "27"}, "iPhone · iOS 27"),
            (
                {"backend": "cloud", "ranDeviceModel": "iPhone 17", "ranOsVersion": "27"},
                "iPhone 17 · iOS 27",
            ),
            (
                {"backend": "physical", "deviceModels": ["iPhone 13"], "osVersion": "18.7"},
                "iPhone 13 · iOS 18.7",
            ),
            (
                {
                    "platform": "android",
                    "label": "Android",
                    "backend": "cloud",
                    "ranDeviceModel": "limdroid_x86_64_only",
                    "ranOsVersion": "15",
                },
                "Android phone · Android 15",
            ),
            (
                {"platform": "android", "label": "Android", "backend": "cloud", "deviceType": "tv"},
                "Android TV",
            ),
            (
                {
                    "platform": "web",
                    "label": "Chrome · Desktop",
                    "browser": "chrome",
                    "viewport": "pc",
                    "browserVersionRequested": "157",
                    "browserVersion": "156.0.7",
                },
                "Chrome 156 · Desktop",
            ),
            (
                {"platform": "web", "label": "Chrome · Desktop", "browser": "chrome"},
                "Chrome · Desktop",
            ),
        ],
    )
    def test_label_names_the_device_and_version(self, fields, label):
        assert target_display_label(_target(**fields)) == label


class TestPlatformLine:
    def test_worst_target_wins_and_counts_add_up(self):
        targets = [
            _target(counters={"headlineStatus": "passed", "passed": 3}),
            _target(counters={"headlineStatus": "critical", "criticals": 1, "warnings": 2}),
            _target(counters={"headlineStatus": "failed", "warnings": 1}),
            _target(platform="web", counters={"headlineStatus": "skipped"}),
        ]

        assert platform_lines(targets) == [
            "iOS: errored · 1 critical · 3 warnings (3 targets)",
            "Web: skipped · 0 criticals · 0 warnings (1 target)",
        ]

    def test_a_running_target_keeps_the_platform_running(self):
        targets = [
            _target(counters={"headlineStatus": "critical", "criticals": 1}),
            _target(counters={"headlineStatus": "running"}),
        ]

        assert platform_lines(targets) == ["iOS: running · 1 critical · 0 warnings (2 targets)"]
