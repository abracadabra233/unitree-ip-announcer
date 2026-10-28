"""Command-line entry point."""

import argparse
from importlib.metadata import version
import logging
from pathlib import Path
import sys

from .announcer import announce, load_sdk
from .config import load_config
from .network import read_ipv4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过宇树 G1 扬声器播报 wlan0 的 IPv4 地址")
    commands = parser.add_subparsers(dest="command", required=True)
    speak = commands.add_parser("announce", help="等待联网后播报一次（次数可配置）")
    speak.add_argument("--dry-run", action="store_true", help="只显示 IP 和播报文本，不调用 SDK")
    doctor = commands.add_parser("doctor", help="检查本地依赖和网卡，不连接机器人语音服务")
    for command in (speak, doctor):
        command.add_argument("--config", type=Path, help="TOML 配置路径；默认读取当前目录的 config.toml")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(args.config)
        if args.command == "announce":
            return announce(config, dry_run=args.dry_run)

        load_sdk()  # Import the binding and native library without creating DDS channels.
        print(f"Python: {sys.version.split()[0]}\nSDK: {version('unitree_sdk2py')}")
        print(f"CycloneDDS Python: {version('cyclonedds')}")
        wlan = read_ipv4()
        dds = read_ipv4(config.audio.dds_interface)
        print(f"播报网卡 wlan0: {wlan or '未就绪'}")
        print(f"SDK 网卡 {config.audio.dds_interface}: {dds or '未就绪'}")
        print("本地检查完成；语音服务和实际音量请用 announce 手动验证。")
        return 0 if wlan and dds else 1
    except KeyboardInterrupt:
        logging.info("已取消")
        return 130
    except Exception as error:
        logging.error("%s: %s", type(error).__name__, error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
