import bpy


class LoginAccountAuth(bpy.types.Operator):
    bl_idname = "bas.login_account_auth"
    bl_label = "Login"

    def execute(self, context):
        from ..studio.account import Account
        Account.get_instance().login()
        return {"FINISHED"}


class LogoutAccountAuth(bpy.types.Operator):
    bl_idname = "bas.logout_account_auth"
    bl_label = "Logout"

    def execute(self, context):
        from ..studio.account import Account
        Account.get_instance().logout()
        return {"FINISHED"}
