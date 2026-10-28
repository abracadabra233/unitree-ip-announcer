# Unitree WLAN IP Announcer

让宇树 G1 用 SDK 的语音接口读出 `wlan0` 的 IPv4 地址，解决 DHCP 分配地址变化后不方便连接机器人的问题。支持手动播报和 systemd 开机播报。

程序固定读取 `wlan0`，等待地址稳定后将数字逐位转成中文，例如文档示例地址 `192.0.2.23` 会读成“一，九，二，点，零，点，二，点，二，三”。默认通过 `eth0` 与机器人的 DDS 语音服务通信；`eth0` 是调用 SDK 的网卡，播报内容始终来自 `wlan0`。

当前适配目标是 Ubuntu 20.04 / ARM64 / 宇树 G1。机器人需要提供 `AudioClient.TtsMaker()` 对应的语音服务，`wlan0` 需要已配置 Wi-Fi 连接。

## 克隆与安装

前置工具为 `uv >= 0.12.3`、`cmake >= 3.16`、Git、C 编译器、Make、curl、tar、sha256sum，以及提供 `ip` 命令的 `iproute2`。Ubuntu 20.04 的系统依赖可这样安装；如果本机已经具备，可以跳过：

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git curl ca-certificates iproute2
```

尚未安装 uv 时，按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)安装，并使用 `uv --version` 确认版本。`bootstrap.sh` 不使用 `sudo`，也不会自动安装 uv 或系统软件包。

克隆到机器人上的普通用户目录，再准备依赖：

```bash
git clone https://github.com/abracadabra233/unitree-ip-announcer.git
cd unitree-ip-announcer
./scripts/bootstrap.sh
```

`bootstrap.sh` 通过 uv 安装 Python `3.11.15`，准备项目自己的 CycloneDDS 原生库，并通过 `uv sync --locked` 安装锁定的 Python 依赖。Python、Python 包、宇树 SDK Git commit、CycloneDDS 版本均由项目固定。原生库放在克隆目录下的 `.deps/cyclonedds`，虚拟环境放在 `.venv`，无需引用机器上其他项目的环境。首次安装需要联网。原生库默认使用 4 个并行构建任务；资源紧张时可运行 `BUILD_JOBS=2 ./scripts/bootstrap.sh`。

Python 包下载默认使用[清华大学 PyPI 镜像](https://pypi.tuna.tsinghua.edu.cn/simple)。Git 源码和 Python 运行时的下载仍使用各自的上游地址。宇树 SDK 固定在官方 commit `814556d15970dd2ecf1c9984e845ca02ab07e206`，CycloneDDS 原生库固定为 `0.10.2`。

完整依赖及镜像配置见 `scripts/bootstrap.sh` 和 `pyproject.toml`。完成安装后，开机服务直接运行本地虚拟环境中的程序，无需现场解析或下载依赖。

## 先手动试听

在项目目录中执行：

```bash
uv run --frozen unitree-ip-announcer announce
```

默认读一次当前 `wlan0` 的地址，成功后退出。第一次验收只需手动运行，由你听到的地址与以下命令显示的 `wlan0` 地址一致即可：

```bash
ip -4 addr show dev wlan0
```

程序收到 SDK 成功响应，只能说明语音请求已被接受；是否实际播出、声音是否清楚，需要现场试听确认。

只预览播报内容；这个模式不加载 SDK，也不发出声音：

```bash
uv run --frozen unitree-ip-announcer announce --dry-run
```

查看本地依赖、网卡和配置检查结果；这个命令会验证 SDK 与原生库可以导入，但不创建 DDS 连接或调用语音服务：

```bash
uv run --frozen unitree-ip-announcer doctor
```

## 配置

未提供 `--config` 时，程序使用当前工作目录的 `config.toml`；文件不存在则使用内置默认值。创建本机配置：

```bash
cp config.example.toml config.toml
```

`config.toml` 已被 Git 忽略。主要配置如下：

```toml
[network]
stable_seconds = 3.0
poll_interval_seconds = 1.0

[audio]
dds_interface = "eth0"
domain_id = 0
speaker_id = 0
rpc_timeout_seconds = 5.0
# volume = 70

[announcement]
repeat = 1
interval_seconds = 15.0

[retry]
interval_seconds = 5.0
attempt_timeout_seconds = 180.0
```

- `stable_seconds`：获得有效 `wlan0` IPv4 后，等待地址连续稳定的时长。
- `dds_interface`：调用语音 SDK 使用的机器人内部通信网卡。
- `volume`：可选的音量值，范围为 0–100。不设置时保留机器人的当前音量。
- `repeat` 和 `interval_seconds`：成功播报的次数和两次播报之间的间隔；默认只播一次。
- `attempt_timeout_seconds`：本轮网络及语音准备的等待预算。启动期间尚未获得地址或语音服务未就绪时，程序会等待、重试；超时后以失败状态退出。

也可以显式指定配置路径：

```bash
uv run --frozen unitree-ip-announcer announce --config ./config.toml
uv run --frozen unitree-ip-announcer doctor --config ./config.toml
```

## 试听成功后，再配置开机启动

以用于安装项目的普通用户运行：

```bash
./scripts/install-service.sh
```

脚本按需调用 `sudo`，使用该普通用户运行服务，将服务安装到 `/etc/systemd/system/unitree-ip-announcer.service`，并启用下次开机自动运行。安装脚本不会立即启动播报。

首次安装会将项目的 `config.toml` 复制到 `/etc/unitree-ip-announcer/config.toml`；如果没有本机配置，则复制 `config.example.toml`。已有的 `/etc` 配置会保留。安装之后，服务读取 `/etc/unitree-ip-announcer/config.toml`，手动命令仍按上面的规则读取配置。

服务在网络启动后运行，由后台进程继续等待 `wlan0` 的 IP 和语音服务就绪，等待过程不会阻塞后续开机目标。成功后显示 `active (exited)`，本次开机不会继续重复播报；如果程序失败退出，systemd 会在 15 秒后重试。

服务使用安装时项目目录中的 `.venv` 和 `.deps`，所以安装后请保留这些文件。若迁移项目，请在新位置重新克隆源码，再运行 `bootstrap.sh` 和安装脚本；虚拟环境及构建缓存包含绝对路径，不要直接搬运。为避免 systemd 路径转义歧义，安装脚本要求项目绝对路径仅含 ASCII 字母、数字、下划线、点、短横线和 `/`；不支持含空格或中文的服务安装路径。

需要直接验证 systemd 服务时，可手动启动：

```bash
sudo systemctl start unitree-ip-announcer.service
```

已成功运行过的服务需使用 `restart` 才会再次播报：

```bash
sudo systemctl restart unitree-ip-announcer.service
```

查看状态和本次开机日志：

```bash
systemctl status unitree-ip-announcer.service
journalctl -u unitree-ip-announcer.service -b --no-pager
```

临时禁用开机播报并停止正在运行的服务：

```bash
sudo systemctl disable --now unitree-ip-announcer.service
```

卸载服务：

```bash
./scripts/uninstall-service.sh
```

卸载会停止并禁用服务、删除 service 文件，保留 `/etc/unitree-ip-announcer/config.toml`、项目源码、原生库和虚拟环境。

## 常见情况

- 一直等待网络：运行 `ip -4 addr show dev wlan0` 确认 Wi-Fi 已连接并分配了有效 IPv4。程序不会选用有线网卡或 Docker 网卡的地址代替。
- 语音调用超时：确认机器人的语音服务已经启动，`audio.dds_interface` 对应连接机器人内部网络的网卡。
- SDK 返回成功但听不到：检查机器人当前音量；可在配置中设置 `volume` 后再手动试听。
- 修改 `/etc` 配置后要立即试听：执行 `sudo systemctl restart unitree-ip-announcer.service`。

项目不修改 DHCP、路由或 Wi-Fi 配置。需要固定 IP 时，可以另外在路由器中设置 DHCP 地址保留。
