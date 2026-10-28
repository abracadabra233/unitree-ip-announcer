"""Small, validated TOML configuration; no third-party parser needed."""

from dataclasses import dataclass, fields
import math
from pathlib import Path
import re
import tomllib


@dataclass(frozen=True)
class Network:
    stable_seconds: float = 3.0
    poll_interval_seconds: float = 1.0


@dataclass(frozen=True)
class Audio:
    dds_interface: str = "eth0"
    domain_id: int = 0
    speaker_id: int = 0
    rpc_timeout_seconds: float = 5.0
    volume: int | None = None


@dataclass(frozen=True)
class Announcement:
    repeat: int = 1
    interval_seconds: float = 15.0


@dataclass(frozen=True)
class Retry:
    interval_seconds: float = 5.0
    attempt_timeout_seconds: float = 180.0


@dataclass(frozen=True)
class Config:
    network: Network = Network()
    audio: Audio = Audio()
    announcement: Announcement = Announcement()
    retry: Retry = Retry()


def _number(name: str, value: object, minimum: float, *, integer: bool = False) -> None:
    types = (int,) if integer else (int, float)
    if type(value) not in types or not math.isfinite(value) or value < minimum:
        kind = "整数" if integer else "有限数值"
        raise ValueError(f"{name} 必须是 >= {minimum} 的{kind}")


def load_config(path: Path | None = None) -> Config:
    """An explicitly supplied path must exist; a missing local config is optional."""
    selected = path if path is not None else Path("config.toml")
    if path is None and not selected.exists():
        data = {}
    else:
        with selected.open("rb") as stream:
            data = tomllib.load(stream)

    sections = {"network": Network, "audio": Audio, "announcement": Announcement, "retry": Retry}
    unknown = data.keys() - sections.keys()
    if unknown:
        raise ValueError(f"未知配置段：{', '.join(sorted(unknown))}")
    values = {}
    for name, cls in sections.items():
        section = data.get(name, {})
        if not isinstance(section, dict):
            raise ValueError(f"{name} 必须是 TOML 配置段")
        extra = section.keys() - {field.name for field in fields(cls)}
        if extra:
            raise ValueError(f"{name} 中有未知配置项：{', '.join(sorted(extra))}")
        values[name] = cls(**section)
    config = Config(**values)

    for name, value, minimum in (
        ("network.stable_seconds", config.network.stable_seconds, 0),
        ("network.poll_interval_seconds", config.network.poll_interval_seconds, 0.1),
        ("audio.rpc_timeout_seconds", config.audio.rpc_timeout_seconds, 0.1),
        ("announcement.interval_seconds", config.announcement.interval_seconds, 0.1),
        ("retry.interval_seconds", config.retry.interval_seconds, 0.1),
        ("retry.attempt_timeout_seconds", config.retry.attempt_timeout_seconds, 1),
    ):
        _number(name, value, minimum)
    for name, value in (("audio.domain_id", config.audio.domain_id),
                        ("audio.speaker_id", config.audio.speaker_id)):
        _number(name, value, 0, integer=True)
    _number("announcement.repeat", config.announcement.repeat, 1, integer=True)
    if config.audio.domain_id > 232:
        raise ValueError("audio.domain_id 必须在 0–232 之间")
    if config.audio.volume is not None:
        _number("audio.volume", config.audio.volume, 0, integer=True)
        if config.audio.volume > 100:
            raise ValueError("audio.volume 必须在 0–100 之间")
    if not isinstance(config.audio.dds_interface, str) or not re.fullmatch(
        r"[a-zA-Z0-9_.:-]{1,15}", config.audio.dds_interface
    ):
        raise ValueError("audio.dds_interface 必须是有效的 Linux 网卡名")
    if config.network.stable_seconds >= config.retry.attempt_timeout_seconds:
        raise ValueError("network.stable_seconds 必须小于 retry.attempt_timeout_seconds")
    return config
