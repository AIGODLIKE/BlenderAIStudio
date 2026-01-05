import bpy
import site
import platform
from pathlib import Path
from urllib.parse import urlparse
from ..logger import logger


class PkgInstaller:
    source = [
        "https://mirrors.aliyun.com/pypi/simple/",
        "https://pypi.tuna.tsinghua.edu.cn/simple/",
        "https://pypi.mirrors.ustc.edu.cn/simple/",
        "https://pypi.python.org/simple/",
        "https://pypi.org/simple",
    ]
    fast_url = ""

    @staticmethod
    def select_pip_source():
        if not PkgInstaller.fast_url:

            import requests

            t, PkgInstaller.fast_url = 999, PkgInstaller.source[0]
            for url in PkgInstaller.source:
                try:
                    tping = requests.get(url, timeout=1).elapsed.total_seconds()
                except Exception as e:
                    logger.warning(e)
                    continue
                if tping < 0.1:
                    PkgInstaller.fast_url = url
                    break
                if tping < t:
                    t, PkgInstaller.fast_url = tping, url
        return PkgInstaller.fast_url

    @staticmethod
    def is_installed(package):
        import importlib

        try:
            return importlib.import_module(package)
        except ModuleNotFoundError:
            return False

    @staticmethod
    def prepare_pip():
        import ensurepip

        if PkgInstaller.is_installed("pip"):
            return True
        try:
            ensurepip.bootstrap()
            return True
        except BaseException:
            ...
        return False

    @staticmethod
    def should_use_user():
        return platform.system() == "Windows" and Path(bpy.app.binary_path).drive.upper().startswith("C:")

    @staticmethod
    def try_install(*packages):
        if not PkgInstaller.prepare_pip():
            return False
        should_use_user = PkgInstaller.should_use_user()
        if should_use_user:
            site.addsitedir(site.getusersitepackages())
        need = [pkg for pkg in packages if not PkgInstaller.is_installed(pkg)]
        from pip._internal import main

        if need:
            url = PkgInstaller.select_pip_source()
        for pkg in need:
            try:
                final_url = urlparse(url)
                # 避免build
                command = ["install", pkg, "-i", url, "--prefer-binary"]
                if should_use_user:
                    command.append("--user")
                command.append("--trusted-host")
                command.append(final_url.netloc)
                main(command)
                if not PkgInstaller.is_installed(pkg):
                    return False
            except Exception:
                return False
        return True
