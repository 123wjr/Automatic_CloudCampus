from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, func, Date, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    nickname = Column(String(128), default="")
    password = Column(String(128), default="")
    amount = Column(Float, default=0.0)
    task_count = Column(Integer, default=0)
    ready_count = Column(Integer, default=0)
    paid = Column(Boolean, default=False)
    fulfilled = Column(Boolean, default=False)
    is_welfare = Column(Boolean, default=False)
    trade_no = Column(String(64), default="")
    context_json = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ExcludedTask(Base):
    __tablename__ = "excluded_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url_pattern = Column(String(512), unique=True, nullable=False)
    note = Column(String(256), default="")
    created_at = Column(DateTime, server_default=func.now())


class CourseConfig(Base):
    __tablename__ = "course_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, nullable=False, unique=True)
    course_name = Column(String(256), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VisitLog(Base):
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    visitor_id = Column(String(128), nullable=False, index=True)
    ip_address = Column(String(64), default="")
    path = Column(String(256), default="/")
    visit_date = Column(Date, server_default=func.current_date())
    created_at = Column(DateTime, server_default=func.now())


class PaymentConfig(Base):
    __tablename__ = "payment_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(64), unique=True, nullable=False, index=True)
    config_value = Column(String(1024), default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WelfareCode(Base):
    __tablename__ = "welfare_codes"
    __allow_unmapped__ = True
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by: Mapped[str] = mapped_column(String(64), default="")
    used_at: Mapped[DateTime] | Mapped[None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), nullable=False, index=True)
    nickname = Column(String(128), default="")
    title = Column(String(512), default="")
    phase = Column(String(32), default="")
    status = Column(String(32), default="")
    message = Column(String(512), default="")
    created_at = Column(DateTime, server_default=func.now())
