import logging
from logging import handlers
from pathlib import Path

DEBUG = True
LOGFILE = Path(__file__).parent.parent / "log.log"
NAME = "BlenderAIStudio"

L = logging.WARNING
if DEBUG:
    L = logging.DEBUG

FMTDICT = {
    'DEBUG': ["[36m", "DBG"],
    'INFO': ["[37m", "INF"],
    'WARN': ["[33m", "WRN"],
    'WARNING': ["[33m", "WRN"],
    'ERROR': ["[31m", "ERR"],
    'CRITICAL': ["[35m", "CRT"],
}


class Handler(logging.StreamHandler):
    with_same_line = False

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream

            is_same_line = getattr(record, "same_line", False)
            was_same_line = self.with_same_line
            self.with_same_line = is_same_line
            # 上次不是 这次是 则打印到新行, 但下次打印到同一行(除非再次设置为False)

            if was_same_line and not is_same_line:
                # 上次是 sameline 但这次不是 则补换行
                stream.write(self.terminator)

            end = "" if is_same_line else self.terminator
            stream.write(msg + end)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


class Filter(logging.Filter):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.translate_func = lambda _: _

    def fill_color(self, color_code="[37m", msg=""):
        return f'\033{color_code}{msg}\033[0m'

    def filter(self, record: logging.LogRecord) -> bool:
        # 颜色map
        color_code, level_shortname = FMTDICT.get(record.levelname, ["[37m", "UN"])
        record.msg = self.translate_func(record.msg)
        record.msg = self.fill_color(color_code, record.msg)
        record.levelname = self.fill_color(color_code, level_shortname)
        return True


class Logger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)

    def set_translate(self, translate_func):
        for handler in self.handlers:
            for filter in handler.filters:
                if not isinstance(filter, Filter):
                    continue
                filter.translate_func = translate_func

    def close(self):
        for h in reversed(self.handlers[:]):
            try:
                try:
                    h.acquire()
                    h.flush()
                    h.close()
                except (OSError, ValueError):
                    pass
                finally:
                    h.release()
            except BaseException:
                ...


def getLogger(name="CLOG", level=logging.INFO, fmt='[%(name)s-%(levelname)s]: %(message)s',
              fmt_date="%H:%M:%S") -> Logger:
    fmter = logging.Formatter('[%(levelname)s]:%(filename)s>%(lineno)s: %(message)s')
    # 按 D/H/M 天时分 保存日志, backupcount 为保留数量
    dfh = handlers.TimedRotatingFileHandler(filename=LOGFILE, when='D', backupCount=2)
    dfh.setLevel(logging.DEBUG)
    dfh.setFormatter(fmter)
    # 命令行打印
    filter = Filter()
    fmter = logging.Formatter(fmt, fmt_date)
    ch = Handler()
    ch.setLevel(level)
    ch.setFormatter(fmter)
    ch.addFilter(filter)

    logger = Logger(name)
    logger.setLevel(level)
    # 防止卸载模块后重新加载导致 重复打印
    if not logger.hasHandlers():
        # 注意添加顺序, ch有filter, 如果fh后添加 则会默认带上ch的filter
        logger.addHandler(dfh)
        logger.addHandler(ch)
    return logger


logger = getLogger(NAME, L)


def close_logger():
    """tips: 关闭日志,在更新插件时日志会占用插件的文件夹"""
    print("close_logger")
    logger.close()
