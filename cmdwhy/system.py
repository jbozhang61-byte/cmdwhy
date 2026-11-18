"""Linux 发行版适配：包管理器、安装/搜索命令、服务管理。"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

FAMILY_BY_ID = {
    "debian": "debian", "ubuntu": "debian", "kali": "debian", "linuxmint": "debian",
    "pop": "debian", "raspbian": "debian", "devuan": "debian",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch", "garuda": "arch",
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora",
    "almalinux": "fedora", "ol": "fedora", "amzn": "fedora",
    "opensuse": "suse", "opensuse-leap": "suse", "opensuse-tumbleweed": "suse", "sles": "suse",
    "alpine": "alpine",
    "gentoo": "gentoo",
    "void": "void",
}

PACKAGE_ALIASES = {
    "python3-venv": {"debian": "python3-venv", "arch": "python", "fedora": "python3", "suse": "python3", "alpine": "python3", "gentoo": "dev-lang/python", "void": "python3"},
    "python3-pip": {"debian": "python3-pip", "arch": "python-pip", "fedora": "python3-pip", "suse": "python3-pip", "alpine": "py3-pip", "gentoo": "dev-python/pip", "void": "python3-pip"},
    "build-essential": {"debian": "build-essential", "arch": "base-devel", "fedora": "gcc gcc-c++ make", "suse": "gcc gcc-c++ make", "alpine": "build-base", "gentoo": "sys-devel/gcc", "void": "base-devel"},
    "command-not-found": {"debian": "command-not-found", "arch": "pkgfile", "fedora": "PackageKit-command-not-found", "suse": "command-not-found", "alpine": "command-not-found", "gentoo": "app-shells/command-not-found", "void": "command-not-found"},
    "docker": {"debian": "docker.io", "arch": "docker", "fedora": "docker", "suse": "docker", "alpine": "docker", "gentoo": "app-containers/docker", "void": "docker"},
}


@dataclass(frozen=True)
class LinuxSystem:
    name: str
    distro_id: str
    family: str
    pkg_manager: str
    init: str = "systemd"

    def package(self, name):
        return PACKAGE_ALIASES.get(name, {}).get(self.family, name)

    def install_command(self, packages, sudo=True):
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        prefix = "sudo " if sudo and not is_root else ""
        pkgs = " ".join(self.package(package) for package in packages)
        if self.pkg_manager == "apt":
            return prefix + "apt install -y " + pkgs
        if self.pkg_manager == "pacman":
            return prefix + "pacman -S --needed --noconfirm " + pkgs
        if self.pkg_manager in ("dnf", "yum"):
            return prefix + self.pkg_manager + " install -y " + pkgs
        if self.pkg_manager == "zypper":
            return prefix + "zypper install -y " + pkgs
        if self.pkg_manager == "apk":
            return prefix + "apk add " + pkgs
        if self.pkg_manager == "emerge":
            return prefix + "emerge " + pkgs
        if self.pkg_manager == "xbps-install":
            return prefix + "xbps-install -y " + pkgs
        return prefix + self.pkg_manager + " install " + pkgs

    def search_command(self, name):
        if self.pkg_manager == "apt":
            return "apt search " + name
        if self.pkg_manager == "pacman":
            return "pacman -Ss " + name
        if self.pkg_manager in ("dnf", "yum"):
            return self.pkg_manager + " search " + name
        if self.pkg_manager == "zypper":
            return "zypper search " + name
        if self.pkg_manager == "apk":
            return "apk search " + name
        if self.pkg_manager == "emerge":
            return "emerge --search " + name
        return "xbps-query -Rs " + name

    def file_provider_command(self, word):
        if self.pkg_manager == "apt":
            return "command-not-found " + word
        if self.pkg_manager == "pacman":
            return "pacman -F " + word
        if self.pkg_manager in ("dnf", "yum"):
            return self.pkg_manager + " provides '*/bin/" + word + "'"
        if self.pkg_manager == "zypper":
            return "zypper search --provides " + word
        if self.pkg_manager == "apk":
            return "apk info -W /usr/bin/" + word
        return ""

    def package_hint(self):
        if self.pkg_manager == "apt":
            return "sudo apt install <包名>"
        if self.pkg_manager == "pacman":
            return "sudo pacman -S --needed <包名>"
        if self.pkg_manager in ("dnf", "yum"):
            return "sudo " + self.pkg_manager + " install <包名>"
        if self.pkg_manager == "zypper":
            return "sudo zypper install <包名>"
        if self.pkg_manager == "apk":
            return "sudo apk add <包名>"
        return "sudo " + self.pkg_manager + " install <包名>"


def _read_release(release=None):
    if release is not None:
        return dict(release)
    data = {}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "=" not in line:
                        continue
                    key, value = line.strip().split("=", 1)
                    data[key] = value.strip().strip('"').strip("'")
            break
        except OSError:
            continue
    return data


def detect(release=None, which=None):
    """识别发行版家族；release 可注入字典用于测试。"""
    if which is None:
        which = shutil.which
    data = _read_release(release)
    ident = (data.get("ID") or "").lower()
    like = (data.get("ID_LIKE") or "").lower()
    family = FAMILY_BY_ID.get(ident)
    if family is None:
        for token in like.split():
            family = FAMILY_BY_ID.get(token)
            if family:
                break
    if family is None:
        if which("apt-get"):
            family = "debian"
        elif which("pacman"):
            family = "arch"
        elif which("dnf"):
            family = "fedora"
        elif which("zypper"):
            family = "suse"
        elif which("apk"):
            family = "alpine"
        elif which("emerge"):
            family = "gentoo"
        elif which("xbps-install"):
            family = "void"
        else:
            family = "unknown"
    manager_by_family = {
        "debian": "apt",
        "arch": "pacman",
        "fedora": "dnf",
        "suse": "zypper",
        "alpine": "apk",
        "gentoo": "emerge",
        "void": "xbps-install",
    }
    manager = manager_by_family.get(family, "apt")
    if family == "fedora" and not which("dnf") and which("yum"):
        manager = "yum"
    name = data.get("PRETTY_NAME") or data.get("NAME") or ident or "Linux"
    return LinuxSystem(
        name=name,
        distro_id=ident,
        family=family,
        pkg_manager=manager,
        init="systemd" if which("systemctl") else "other",
    )


def install_command(packages, sudo=True):
    return detect().install_command(packages, sudo=sudo)


def package_hint():
    return detect().package_hint()


def python_venv_package():
    return detect().package("python3-venv")
