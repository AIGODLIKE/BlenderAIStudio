from .pkg_installer import PkgInstaller

__all__ = [
    "PkgInstaller",
]


def get_pref():
    from ... import __package__ as base_name
    return bpy.context.preferences.addons[base_name].preferences


def register():
    pass


def unregister():
    pass
