#!/usr/bin/env bash
# Install and enable the service. Intentionally do not start it here.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
service_name="unitree-ip-announcer.service"
config_dir="/etc/unitree-ip-announcer"
config_path="$config_dir/config.toml"
unit_path="/etc/systemd/system/$service_name"

fail() {
    printf '错误：%s\n' "$*" >&2
    exit 1
}

# Every substituted value must be safe as an unquoted systemd path/identifier.
[[ "$project_dir" =~ ^/[A-Za-z0-9_./-]+$ ]] || \
    fail "systemd 安装路径只支持 ASCII 字母、数字、下划线、点、短横线和 /；请移动项目后重试。"
command -v systemctl >/dev/null || fail "此系统没有 systemctl。"

sudo_cmd=()
if [[ "$EUID" -eq 0 ]]; then
    run_user="${SUDO_USER:-}"
    [[ -n "$run_user" && "$run_user" != root ]] || \
        fail "请以普通用户运行此脚本；需要时脚本会调用 sudo。"
else
    run_user="$(id -un)"
    command -v sudo >/dev/null || fail "安装服务需要 sudo。"
    sudo_cmd=(sudo)
fi
run_group="$(id -gn "$run_user")"
[[ "$run_user" =~ ^[A-Za-z0-9_.-]+$ && "$run_group" =~ ^[A-Za-z0-9_.-]+$ ]] || \
    fail "用户名或组名包含本安装脚本不支持的字符。"
[[ -x "$project_dir/.venv/bin/unitree-ip-announcer" ]] || \
    fail "尚未创建运行环境，请先执行 ./scripts/bootstrap.sh。"
[[ -d "$project_dir/.deps/cyclonedds/lib" ]] || \
    fail "缺少项目本地 CycloneDDS 动态库，请先执行 ./scripts/bootstrap.sh。"
[[ -f "$project_dir/deploy/$service_name.in" ]] || fail "找不到服务模板。"
[[ -f "$project_dir/config.example.toml" ]] || fail "找不到配置示例。"

temporary_dir="$(mktemp -d)"
trap 'rm -rf -- "$temporary_dir"' EXIT
rendered_unit="$temporary_dir/$service_name"
sed \
    -e "s|@PROJECT_DIR@|$project_dir|g" \
    -e "s|@RUN_USER@|$run_user|g" \
    -e "s|@RUN_GROUP@|$run_group|g" \
    "$project_dir/deploy/$service_name.in" > "$rendered_unit"
if command -v systemd-analyze >/dev/null; then
    systemd-analyze verify "$rendered_unit"
fi

"${sudo_cmd[@]}" install -d -m 0755 "$config_dir"
if "${sudo_cmd[@]}" test -e "$config_path"; then
    printf '保留现有配置：%s\n' "$config_path"
else
    initial_config="$project_dir/config.example.toml"
    if [[ -f "$project_dir/config.toml" ]]; then
        initial_config="$project_dir/config.toml"
    fi
    "${sudo_cmd[@]}" install -m 0644 "$initial_config" "$config_path"
    printf '已安装配置：%s（来源：%s）\n' "$config_path" "$initial_config"
fi
"${sudo_cmd[@]}" install -m 0644 "$rendered_unit" "$unit_path"
"${sudo_cmd[@]}" systemctl daemon-reload
"${sudo_cmd[@]}" systemctl enable "$service_name"

printf '\n已启用开机播报，运行用户：%s。此次安装没有启动播报。\n' "$run_user"
printf '配置文件：%s\n' "$config_path"
printf '服务绑定的项目目录：%s（请保留此目录及虚拟环境）\n' "$project_dir"
printf '如需现在手动运行服务：sudo systemctl start %s\n' "$service_name"
printf '查看日志：journalctl -u %s -b --no-pager\n' "$service_name"
