import bpy


class UploadErrorReport(bpy.types.Operator):
    bl_idname = "bas.upload_error_report"
    bl_label = "Upload Error Report"
    bl_description = "Collect logs and upload to server"

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            from ..studio.account.error_report import upload_error_report_async

            self.report({"INFO"}, "Uploading logs...")
            upload_error_report_async(self)
            return {"FINISHED"}
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
