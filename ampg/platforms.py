from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import os
import platform


@dataclass(frozen=True)
class PlatformProvider:
    name: str
    process_supervisor: str
    can_manage_daemons: bool
    can_write_system_config: bool
    state_root: Path
    notes: tuple[str, ...] = ()


PLATFORM_NAMES = (
    "android-termux",
    "linux-systemd",
    "linux-user",
    "macos-launchd",
    "unknown",
)


def detect_platform(
    env: Mapping[str, str] | None = None,
    *,
    system_name: str | None = None,
    path_exists: Callable[[Path], bool] | None = None,
) -> PlatformProvider:
    environ = env if env is not None else os.environ
    system = system_name or platform.system()
    exists = path_exists or Path.exists

    if _looks_like_termux(environ):
        prefix = Path(environ.get("PREFIX", "/data/data/com.termux/files/usr"))
        return PlatformProvider(
            name="android-termux",
            process_supervisor="termux-services",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=prefix / "var/lib/ampg",
            notes=(
                "User-space daemons only.",
                "Public ports and battery/background policy remain device-owned.",
            ),
        )

    if system == "Linux":
        if exists(Path("/run/systemd/system")):
            return PlatformProvider(
                name="linux-systemd",
                process_supervisor="systemd",
                can_manage_daemons=True,
                can_write_system_config=True,
                state_root=Path("/var/lib/ampg"),
                notes=("System service management is available after operator approval.",),
            )
        return PlatformProvider(
            name="linux-user",
            process_supervisor="user-process",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=_home(environ) / ".local/state/ampg",
            notes=("Runs AMPG-owned daemons in user space.",),
        )

    if system == "Darwin":
        return PlatformProvider(
            name="macos-launchd",
            process_supervisor="launchd-user",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=_home(environ) / "Library/Application Support/AMPG",
            notes=("Uses user LaunchAgents or foreground processes.",),
        )

    return PlatformProvider(
        name="unknown",
        process_supervisor="manual",
        can_manage_daemons=False,
        can_write_system_config=False,
        state_root=_home(environ) / ".ampg",
        notes=("AMPG can render and plan, but daemon management is disabled.",),
    )


def platform_by_name(name: str) -> PlatformProvider:
    if name == "android-termux":
        return PlatformProvider(
            name=name,
            process_supervisor="termux-services",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=Path("/data/data/com.termux/files/usr/var/lib/ampg"),
            notes=("User-space daemons only.",),
        )
    if name == "linux-systemd":
        return PlatformProvider(
            name=name,
            process_supervisor="systemd",
            can_manage_daemons=True,
            can_write_system_config=True,
            state_root=Path("/var/lib/ampg"),
            notes=("System service management is available after operator approval.",),
        )
    if name == "linux-user":
        return PlatformProvider(
            name=name,
            process_supervisor="user-process",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=Path("~/.local/state/ampg").expanduser(),
            notes=("Runs AMPG-owned daemons in user space.",),
        )
    if name == "macos-launchd":
        return PlatformProvider(
            name=name,
            process_supervisor="launchd-user",
            can_manage_daemons=True,
            can_write_system_config=False,
            state_root=Path("~/Library/Application Support/AMPG").expanduser(),
            notes=("Uses user LaunchAgents or foreground processes.",),
        )
    if name == "unknown":
        return PlatformProvider(
            name=name,
            process_supervisor="manual",
            can_manage_daemons=False,
            can_write_system_config=False,
            state_root=Path("~/.ampg").expanduser(),
            notes=("Daemon management is disabled.",),
        )
    raise ValueError(f"unknown platform provider {name!r}")


def _looks_like_termux(env: Mapping[str, str]) -> bool:
    prefix = env.get("PREFIX", "")
    return (
        "com.termux" in prefix
        or bool(env.get("TERMUX_VERSION"))
        or (bool(env.get("ANDROID_ROOT")) and "com.termux" in env.get("HOME", ""))
    )


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME", "~")).expanduser()
