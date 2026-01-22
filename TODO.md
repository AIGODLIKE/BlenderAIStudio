待处理

1.3d界面ui如果图片不存在时的复制图片处理bug
2.多开blender时部分用户会出现崩溃问题  src/utils/async_request.py:L25 src/studio/gui/__init__.py:11
3.超大图片输入时会出现
[BlenderAIStudio-INF]: on_failed {'task': <BlenderAIStudio.src.studio.tasks.gemini_tasks.AccountGeminiImageEditTask object at 0x000001A74F45D0D0>, 'result': TaskResult(success=False, data=None, error=GeminiAPIError('Bad request (400),Please check the network and proxy'), error_message='图片编辑失败: Bad request (400),Please check the network and proxy', metadata={})}
[BlenderAIStudio-INF]: Bad request (400),Please check the network and proxy
