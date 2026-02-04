import os
import threading

import bpy


# 定义一个简单的线程类来封装请求任务
class RequestThread(threading.Thread):
    def __init__(self, url, callback_func, *args, **kwargs):
        super().__init__(daemon=True)
        self.url = url
        # callback_func是一个函数，它将在主线程被调用，并接收（结果， 错误）两个参数
        self.callback = callback_func
        self.args = args
        self.kwargs = kwargs

        self.response = None
        self.result = None
        self.error = None
        self.timeout = kwargs.get("timeout", 15)

    def run(self):
        """线程运行的核心方法（在子线程中执行）"""
        try:
            self.request()
            # TODO 多开bug
            # def r(): # 修了这个bug会有另一个bug出现
            # bpy.app.timers.register(r, first_interval=round(random.uniform(1.0, 10.0), 2))  # 需要随机延迟，不然会导致多开的时候闪退
        except Exception as e:
            self.error = e
        finally:
            # 请求完成后，安排回调函数到主线程
            bpy.app.timers.register(lambda: self.callback(self.result, self.error, *self.args, **self.kwargs))

    def request(self):
        ...


class GetRequestThread(RequestThread):
    """用法

    VERSION_URL = f"https://api-addon.acggit.com/v1/sys/version"
    def on_request_finished(result, error):
        if error:
            print(f"[线程请求失败] {type(error).__name__}: {error}")
            # 可以在这里更新UI，显示错误信息（因为已在主线程）
            # 例如：bpy.context.scene.request_status = "Failed"
        else:
            print(f"[线程请求成功] 获取到 {len(result)} 字符的数据")
            print(f"数据预览: {result[:200]}")
    RequestThread(VERSION_URL, on_request_finished).start()
    """

    def __init__(self, url, callback_func, *args, **kwargs):
        super().__init__(url, callback_func, *args, **kwargs)
        self.daemon = True

    def request(self):
        import requests
        # requests = import_requests()
        response = requests.get(self.url, timeout=15)
        response.raise_for_status()  # 检查HTTP错误
        self.response = response
        self.result = response.text


class PostRequestThread(RequestThread):
    """用法

    VERSION_URL = f"https://api-addon.acggit.com/v1/sys/version"
    def on_request_finished(result, error):
        if error:
            print(f"[线程请求失败] {type(error).__name__}: {error}")
            # 可以在这里更新UI，显示错误信息（因为已在主线程）
            # 例如：bpy.context.scene.request_status = "Failed"
        else:
            print(f"[线程请求成功] 获取到 {len(result)} 字符的数据")
            print(f"数据预览: {result[:200]}")
    RequestThread(VERSION_URL, on_request_finished).start()
    """

    def __init__(self, url, callback_func, headers, payload, *args, **kwargs):
        super().__init__(url, callback_func, *args, **kwargs)
        self.daemon = True
        self.headers = headers
        self.payload = payload

    def request(self):
        import requests
        response = requests.post(self.url, headers=self.headers, json=self.payload, timeout=self.timeout)
        response.raise_for_status()  # 检查HTTP错误
        self.response = response
        self.result = response.text


class DownloadZipRequestThread(RequestThread):
    def __init__(self, url, download_path, callback_func, *args, **kwargs):
        super().__init__(url, callback_func, *args, **kwargs)
        self.download_path = download_path

    def request(self):
        import requests
        response = requests.get(self.url, stream=True, timeout=30)
        response.raise_for_status()
        os.makedirs(os.path.dirname(self.download_path), exist_ok=True)

        with open(self.download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        self.result = self.download_path
