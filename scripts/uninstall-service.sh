#!/usr/bin/env bash
# Preserve /etc/unitree-ip-announcer/config.toml for a later reinstall.
set -euo pipefail

service_name="unitree-ip-announcer.service"
unit_path="/etc/systemd/system/$service_name"
command -v systemctl >/dev/null || {
    printf '错误：此系统没有 systemctl。\n' >&2
    exit 1
}
sudo_cmd=()
if [[ "$EUID" -ne 0 ]]; then
    command -v sudo >/dev/null || {
        printf '错误：卸载服务需要 sudo。\n' >&2
        exit 1
    }
    sudo_cmd=(sudo)
fi

if [[ -e "$unit_path" || -L "$unit_path" ]]; then
    "${sudo_cmd[@]}" systemctl disable --now "$service_name"
    "${sudo_cmd[@]}" rm -f -- "$unit_path"
    "${sudo_cmd[@]}" systemctl daemon-reload
    "${sudo_cmd[@]}" systemctl reset-failed "$service_name" 2>/dev/null || true
    printf '已停止并卸载 %s。\n' "$service_name"
else
    printf '未找到 %s，无需卸载。\n' "$unit_path"
fi
printf '配置保留在 /etc/unitree-ip-announcer/config.toml；项目文件和虚拟环境也会保留。\n'
