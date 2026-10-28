"""Readiness, retry and TTS orchestration, with lazy SDK imports."""

import logging
import os
from pathlib import Path
import sys
import time

from .config import Config
from .network import StableAddress, read_ipv4


LOG = logging.getLogger(__name__)
DIGITS = str.maketrans("0123456789", "零一二三四五六七八九")


def speech_text(address: str) -> str:
    # Chinese digit names prevent TTS from reading an octet as a whole number.
    spoken = "，点，".join("，".join(part.translate(DIGITS)) for part in address.split("."))
    return f"无线网络地址是：{spoken}。"


def load_sdk():
    # bootstrap puts the native library beside this project's .venv. Override
    # unrelated shell settings when this self-contained installation is present.
    native_home = Path(sys.prefix).parent / ".deps" / "cyclonedds"
    if (native_home / "lib" / "libddsc.so").is_file():
        os.environ["CYCLONEDDS_HOME"] = str(native_home)
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
    return ChannelFactoryInitialize, AudioClient


def announce(config: Config, *, dry_run: bool = False) -> int:
    sdk = None if dry_run else load_sdk()
    deadline = time.monotonic() + config.retry.attempt_timeout_seconds
    stable = StableAddress(config.network.stable_seconds)
    client = None
    completed = 0
    last_wait = None
    last_error = "wlan0 尚未获得稳定的 IPv4 地址"

    def pause(seconds: float) -> None:
        time.sleep(max(0, min(seconds, deadline - time.monotonic())))

    def bound_rpc() -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("本次等待预算已用尽")
        # SDK may spend one timeout sending and another awaiting the reply.
        client.SetTimeout(min(config.audio.rpc_timeout_seconds, remaining / 2))

    LOG.info("等待 wlan0 的 IPv4 地址稳定 %.1f 秒", config.network.stable_seconds)
    while time.monotonic() < deadline:
        address = stable.observe(read_ipv4(), time.monotonic())
        if address is None:
            last_error = "wlan0 尚未获得稳定的 IPv4 地址"
            if last_wait != stable.address:
                LOG.info("wlan0 当前地址：%s", stable.address or "未就绪")
                last_wait = stable.address
            pause(config.network.poll_interval_seconds)
            continue
        text = speech_text(address)
        if dry_run:
            print(f"wlan0 IPv4: {address}\n播报内容: {text}\n预览完成，未调用语音接口。")
            return 0
        try:
            if client is None:
                if read_ipv4(config.audio.dds_interface) is None:
                    raise RuntimeError(f"SDK 网卡 {config.audio.dds_interface} 尚未获得 IPv4 地址")
                initialize, audio_class = sdk
                initialize(config.audio.domain_id, config.audio.dds_interface)
                client = audio_class()
                client.Init()
            bound_rpc()
            code, volume = client.GetVolume()
            if code != 0:
                raise RuntimeError(f"语音服务未就绪，GetVolume 返回 {code}")
            if config.audio.volume is not None:
                bound_rpc()
                code = client.SetVolume(config.audio.volume)
                if code != 0:
                    raise RuntimeError(f"SetVolume 返回 {code}")
            elif volume and volume.get("volume") == 0:
                LOG.warning("机器人当前音量为 0；可在配置中设置 audio.volume")

            # DDS discovery/RPC can take time. Recheck so DHCP changes during
            # that wait do not cause a stale address to be announced.
            current = stable.observe(read_ipv4(), time.monotonic())
            if current != address:
                LOG.info("wlan0 地址已变化，重新等待稳定")
                continue
            bound_rpc()
            LOG.info("播报 wlan0=%s（第 %d/%d 遍）", address, completed + 1, config.announcement.repeat)
            code = client.TtsMaker(text, config.audio.speaker_id)
            if code != 0:
                raise RuntimeError(f"TtsMaker 返回 {code}")
        except Exception as error:
            last_error = str(error)
            LOG.warning("%s；稍后重试", last_error)
            pause(config.retry.interval_seconds)
            continue

        completed += 1
        if completed >= config.announcement.repeat:
            LOG.info("语音接口已接受播报请求：%s", address)
            return 0
        pause(config.announcement.interval_seconds)

    LOG.error("等待超时（%.1f 秒）：%s", config.retry.attempt_timeout_seconds, last_error)
    return 1
