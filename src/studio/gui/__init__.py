from ...utils import PkgInstaller

from ...utils import debug_time


@debug_time
def register():
    PkgInstaller.try_install("slimgui")


def unregister():
    pass
