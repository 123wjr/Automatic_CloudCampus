from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    account: str
    password: str
    course_id: Optional[int] = None


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    nickname: str
    user_id: str
    cookie: str
    sesskey: str


class CourseInfo(BaseModel):
    course_id: str
    course_name: str


class TaskItem(BaseModel):
    index: int
    title: str
    url: str


class TaskItemWithStatus(TaskItem):
    has_packet: bool = False
    excluded: bool = False
    category_id: int
    """
    1: view (include mark as done)
    2. resend
    """


class ProgressResponse(BaseModel):
    nickname: str
    user_id: str
    tasks: list[TaskItemWithStatus]
    total_tasks: int
    valid_tasks: int
    skipped_tasks: int
    excluded_tasks: int
    course_id: str


class PaymentRequest(BaseModel):
    amount: float = 0.0
    task_count: int
    ready_count: int
    total_tasks: int = 0
    user_id: str
    nickname: str = ""
    client_ip: str = ""
    tasks: list[TaskItemWithStatus] = Field(default_factory=list)


class PaymentResponse(BaseModel):
    order_id: str
    pay_url: str = ""
    qr_base64: str = ""
    amount: float
    base_price: float = 0.0


class PaymentStatusResponse(BaseModel):
    order_id: str
    status: str
    paid: bool


class ExecuteRequest(BaseModel):
    tasks: list[TaskItem]
    user_info: UserInfo
    order_id: str


class ExecuteResponse(BaseModel):
    session_id: str
    status: str


class TaskProgress(BaseModel):
    session_id: str
    current: int
    total: int
    title: str
    status: str
    message: str


class ExcludedTaskItem(BaseModel):
    id: Optional[int] = None
    url_pattern: str
    note: str = ""


class CourseConfigItem(BaseModel):
    id: Optional[int] = None
    course_id: int
    course_name: str = ""
    is_active: bool = True


class AdminStats(BaseModel):
    total_visits: int
    today_visits: int
    total_orders: int
    today_orders: int
    total_revenue: float = 0.0
    recent_orders: list[dict] = []


class PaymentConfigSchema(BaseModel):
    pid: str = ""
    key: str = ""
    sitename: str = "AutoCC"
    base_price: float = 20.0
    notify_url: str = ""
    return_url: str = ""
