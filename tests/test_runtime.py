"""Offline checks: never create DDS channels or contact the robot."""

from contextlib import redirect_stdout
from dataclasses import replace
import io
import unittest
from unittest.mock import Mock, patch

from unitree_ip_announcer import announcer
from unitree_ip_announcer.config import Config, Network, Retry


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.address = "192.0.2.24"
        self.client = Mock()
        self.client.GetVolume.return_value = (0, {"volume": 50})
        self.client.TtsMaker.return_value = 0
        self.initialize = Mock()
        self.audio_class = Mock(return_value=self.client)
        self.config = Config(
            network=Network(stable_seconds=1.0, poll_interval_seconds=1.0),
            retry=Retry(interval_seconds=2.0, attempt_timeout_seconds=10.0),
        )
        self.enterContext(patch.object(announcer.time, "monotonic", self.clock.monotonic))
        self.enterContext(patch.object(announcer.time, "sleep", self.clock.sleep))
        self.enterContext(patch.object(announcer, "read_ipv4", self.read_address))
        self.load_sdk = self.enterContext(patch.object(
            announcer, "load_sdk", return_value=(self.initialize, self.audio_class)
        ))

    def read_address(self, interface="wlan0"):
        return self.address if interface == "wlan0" else "198.51.100.2"

    def test_dry_run_does_not_load_sdk(self):
        self.load_sdk.side_effect = AssertionError("dry-run must not import the SDK")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(announcer.announce(self.config, dry_run=True), 0)
        self.assertIn("wlan0 IPv4: 192.0.2.24", output.getvalue())
        self.initialize.assert_not_called()
        self.client.TtsMaker.assert_not_called()

    def test_dhcp_change_during_readiness_never_announces_old_address(self):
        def ready():
            self.address = "192.0.2.25"
            return 0, {"volume": 50}

        self.client.GetVolume.side_effect = ready
        self.assertEqual(announcer.announce(self.config), 0)
        self.client.TtsMaker.assert_called_once_with(
            "无线网络地址是：一，九，二，点，零，点，二，点，二，五。", 0
        )
        self.assertGreaterEqual(self.clock.now, 2.0)

    def test_audio_readiness_failure_retries_before_speaking(self):
        self.client.GetVolume.side_effect = [(3102, {}), (0, {"volume": 50})]
        self.assertEqual(announcer.announce(self.config), 0)
        self.assertEqual(self.client.GetVolume.call_count, 2)
        self.assertGreaterEqual(self.clock.now, 3.0)
        self.client.TtsMaker.assert_called_once()

    def test_no_wlan_address_exhausts_budget_without_dds_initialization(self):
        self.address = None
        config = replace(self.config, retry=Retry(interval_seconds=2.0, attempt_timeout_seconds=3.0))
        self.assertEqual(announcer.announce(config), 1)
        self.assertEqual(self.clock.now, 3.0)
        self.initialize.assert_not_called()
        self.client.TtsMaker.assert_not_called()

    def test_audio_rpc_timeout_is_limited_to_remaining_budget(self):
        config = replace(self.config, retry=Retry(interval_seconds=2.0, attempt_timeout_seconds=3.0))

        def unavailable():
            timeout = self.client.SetTimeout.call_args.args[0]
            self.clock.sleep(timeout * 2)
            return 3102, {}

        self.client.GetVolume.side_effect = unavailable
        self.assertEqual(announcer.announce(config), 1)
        self.assertEqual(self.clock.now, 3.0)
        self.client.TtsMaker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
