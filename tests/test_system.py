import unittest

from cmdwhy import system


class SystemTest(unittest.TestCase):
    def detect(self, ident, like=""):
        return system.detect(
            {"ID": ident, "ID_LIKE": like, "PRETTY_NAME": ident.title()},
            which=lambda name: None,
        )

    def test_families(self):
        cases = [
            ("ubuntu", "", "debian", "apt"),
            ("kali", "", "debian", "apt"),
            ("arch", "", "arch", "pacman"),
            ("manjaro", "", "arch", "pacman"),
            ("fedora", "", "fedora", "dnf"),
            ("centos", "rhel fedora", "fedora", "dnf"),
            ("rocky", "rhel", "fedora", "dnf"),
            ("opensuse-leap", "suse", "suse", "zypper"),
            ("alpine", "", "alpine", "apk"),
        ]
        for ident, like, family, manager in cases:
            distro = self.detect(ident, like)
            self.assertEqual(distro.family, family, ident)
            self.assertEqual(distro.pkg_manager, manager, ident)

    def test_install_commands(self):
        arch = self.detect("arch")
        self.assertIn("pacman -S", arch.install_command(["git"]))
        ubuntu = self.detect("ubuntu")
        self.assertIn("apt install", ubuntu.install_command(["git"]))
        fedora = self.detect("fedora")
        self.assertIn("dnf install", fedora.install_command(["git"]))
        alpine = self.detect("alpine")
        self.assertIn("apk add", alpine.install_command(["git"]))

    def test_package_aliases(self):
        arch = self.detect("arch")
        self.assertEqual(arch.package("python3-venv"), "python")
        self.assertEqual(arch.package("python3-pip"), "python-pip")
        alpine = self.detect("alpine")
        self.assertEqual(alpine.package("python3-pip"), "py3-pip")
        self.assertEqual(alpine.package("build-essential"), "build-base")

    def test_provider_commands(self):
        self.assertIn("pacman -F", self.detect("arch").file_provider_command("jq"))
        self.assertIn("dnf provides", self.detect("fedora").file_provider_command("jq"))
        self.assertIn("command-not-found", self.detect("ubuntu").file_provider_command("jq"))
        self.assertIn("zypper", self.detect("opensuse").file_provider_command("jq"))


if __name__ == "__main__":
    unittest.main()
