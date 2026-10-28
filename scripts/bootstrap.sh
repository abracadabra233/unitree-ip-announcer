#!/usr/bin/env bash
# Prepare this checkout only; never installs a service or sends robot commands.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$project_dir"

if (( $# != 0 )); then
    printf 'Usage: %s\nOptional environment: BUILD_JOBS=4 (native build parallelism).\n' "$0" >&2
    exit 2
fi

missing=()
for command in uv git cmake cc make curl tar sha256sum ip; do
    command -v "$command" >/dev/null 2>&1 || missing+=("$command")
done
if (( ${#missing[@]} )); then
    printf 'Missing required tools: %s\n' "${missing[*]}" >&2
    printf 'Ubuntu system packages: build-essential cmake git curl ca-certificates iproute2.\n' >&2
    printf 'Install uv >= 0.12.3 separately; this script does not run sudo or change system packages.\n' >&2
    exit 1
fi

build_jobs="${BUILD_JOBS:-4}"
if [[ ! "$build_jobs" =~ ^[1-9][0-9]*$ ]]; then
    printf 'BUILD_JOBS must be a positive integer.\n' >&2
    exit 2
fi

# Official CycloneDDS 0.10.2 tag, pinned to its resolved commit and archive hash.
cyclone_commit='9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd'
cyclone_sha256='fea1397b081de990b21f4ae9fa496d7911734a479f90a41acbbdcff67086afec'
deps_dir="$project_dir/.deps"
install_dir="$deps_dir/cyclonedds"
archive="$deps_dir/downloads/cyclonedds-$cyclone_commit.tar.gz"
build_stamp="0.10.2:$cyclone_commit:$cyclone_sha256:release-lib-v2"
mkdir -p -- "$deps_dir/downloads"

if [[ ! -f "$install_dir/.build-stamp" ]] \
    || [[ "$(cat -- "$install_dir/.build-stamp")" != "$build_stamp" ]] \
    || [[ ! -f "$install_dir/lib/libddsc.so" ]] \
    || [[ ! -f "$install_dir/include/dds/dds.h" ]]; then
    if [[ ! -f "$archive" ]] || ! printf '%s  %s\n' "$cyclone_sha256" "$archive" | sha256sum --check --status; then
        printf 'Downloading CycloneDDS 0.10.2 (%s)...\n' "$cyclone_commit"
        curl --fail --location --retry 3 --connect-timeout 30 --max-time 600 \
            --output "$archive.part" \
            "https://codeload.github.com/eclipse-cyclonedds/cyclonedds/tar.gz/$cyclone_commit"
        printf '%s  %s\n' "$cyclone_sha256" "$archive.part" | sha256sum --check
        mv -- "$archive.part" "$archive"
    fi
    # CycloneDDS 0.10.2's generated-source CMake rules mishandle spaces in the
    # source path. Build in a clean, space-free temporary directory and install
    # back into this checkout (which may contain spaces).
    native_work="$(mktemp -d /tmp/unitree-ip-announcer-cyclone.XXXXXX)"
    trap 'rm -rf -- "$native_work"' EXIT
    tar -xzf "$archive" -C "$native_work"
    source_dir="$native_work/cyclonedds-$cyclone_commit"
    build_dir="$native_work/build"
    cmake -S "$source_dir" -B "$build_dir" -G 'Unix Makefiles' \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$install_dir" \
        -DCMAKE_INSTALL_LIBDIR=lib \
        -DBUILD_EXAMPLES=OFF -DBUILD_TESTING=OFF -DBUILD_DDSPERF=OFF \
        -DBUILD_IDLC=ON -DENABLE_SHM=OFF -DENABLE_SSL=OFF -DENABLE_SECURITY=OFF
    cmake --build "$build_dir" --parallel "$build_jobs"
    cmake --install "$build_dir"
    printf '%s\n' "$build_stamp" > "$install_dir/.build-stamp"
    rm -rf -- "$native_work"
    trap - EXIT
else
    printf 'Using the verified CycloneDDS 0.10.2 build in %s\n' "$install_dir"
fi

export CYCLONEDDS_HOME="$install_dir"
export LD_LIBRARY_PATH="$install_dir/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export UV_PROJECT_ENVIRONMENT="$project_dir/.venv"
uv python install "$(cat .python-version)"
uv sync --locked

printf '\nEnvironment ready. No audio has been played and no service has been installed.\n'
printf 'Preview: uv run --frozen unitree-ip-announcer announce --dry-run\n'
printf 'Manual playback: uv run --frozen unitree-ip-announcer announce\n'
