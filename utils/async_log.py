import queue
import threading

_log_queue = queue.Queue()
_app = None
_worker_started = False


def init_async_log_writer(app):
    """在 app.py 中调用，启动后台日志写入线程"""
    global _app, _worker_started
    _app = app
    if _worker_started:
        return
    _worker_started = True
    worker = threading.Thread(target=_log_writer, daemon=True, name="async-log-writer")
    worker.start()


def _log_writer():
    from models.database import db
    while True:
        log_entry = _log_queue.get()
        if log_entry is None:
            break
        try:
            with _app.app_context():
                db.session.add(log_entry)
                db.session.commit()
        except Exception:
            pass


def write_log(log_entry):
    """非阻塞写入日志，将 Log 对象放入队列由后台线程写入数据库"""
    _log_queue.put(log_entry)
