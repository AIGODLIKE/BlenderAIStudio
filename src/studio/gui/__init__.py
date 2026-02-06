from ...utils import PkgInstaller


def register():
    PkgInstaller.try_install("slimgui")


def unregister():
    pass
