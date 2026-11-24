"""pytest 全局夹具。

在收集任何测试之前先把后端包加入 sys.path，并确保 SQLite 表结构已经建好，
这样测试不依赖仓库里是否已经存在 backend/data/app.db（该文件不入库）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import Base, engine  # noqa: E402
from app.models import db_models  # noqa: E402,F401  导入即注册全部表定义

Base.metadata.create_all(bind=engine)
