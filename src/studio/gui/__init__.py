from threading import Thread


def register():
    def install():
        from ...utils import PkgInstaller
        PkgInstaller.try_install("slimgui")

    Thread(target=install, daemon=True).start()


def unregister():
    pass
