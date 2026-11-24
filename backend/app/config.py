import os
from pathlib import Path

# computed paths (kept as module-level constants)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "Raw"
DB_PATH = BASE_DIR / "backend" / "data" / "app.db"
os.makedirs(BASE_DIR / "backend" / "data", exist_ok=True)

# 手工加载仓库根目录的 .env / .env.local（与启动时的当前工作目录无关），
# 并把历史遗留的 AUTOCC_ 前缀变量映射成不带前缀的字段名，两种写法都兼容。
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR / ".env.local", override=True)
except ImportError:  # pragma: no cover - python-dotenv 随 pydantic-settings 一起安装
    pass

_ENV_PREFIX = "AUTOCC_"
for _key, _value in list(os.environ.items()):
    if _key.startswith(_ENV_PREFIX) and len(_key) > len(_ENV_PREFIX):
        os.environ.setdefault(_key[len(_ENV_PREFIX):], _value)

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    CLOUDCAMPUS_BASE: str = "https://www.cloudcampus.com.cn"
    GRADE_URL_TEMPLATE: str = "{base}/grade/report/user/index.php?id={course_id}"
    MANUAL_MARK_URL: str = "https://www.cloudcampus.com.cn/lib/ajax/service.php"

    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )

    DEFAULT_COURSE_ID: int = 11881

    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""

    # 以原始字符串读取，避免 pydantic-settings 2.5 对 list 字段做 JSON 预解析而启动崩溃。
    # 支持逗号分隔；在导出层拆分为 list（见下方 CORS_ORIGINS / DEFAULT_EXCLUDED_TASKS）。
    DEFAULT_EXCLUDED_TASKS: str = ""

    # 留空表示仅允许本地开发地址（见 main.py）；生产环境请在 .env 中填写真实域名
    CORS_ORIGINS: str = ""

    RATE_LIMIT_LOGIN: int = 5
    RATE_LIMIT_WINDOW: int = 60

    PAYMENT_PID: str = ""
    PAYMENT_KEY: str = ""
    PAYMENT_SITENAME: str = "AutoCC"
    PAYMENT_BASE_PRICE: float = 20.0
    # 留空表示未配置支付回调地址；生产环境请在 .env 中填写公网域名
    PAYMENT_NOTIFY_PATH: str = ""
    PAYMENT_RETURN_URL: str = ""

    TRUSTED_HOST: str = ""

    ZPAY_API_URL: str = "https://zpayz.cn/mapi.php"
    ZPAY_ORDER_QUERY_URL: str = "https://zpayz.cn/api.php?act=order"

    # 对外公开的客服联系邮箱（非密钥，可用 CONTACT_EMAIL 覆盖）
    CONTACT_EMAIL: str = "support@example.com"

    # .env 已在上方用 load_dotenv 手动加载，这里不再让 pydantic 重复读取，
    # 以免受启动目录影响。
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
    )


def _split_csv(v: str) -> list[str]:
    if not v:
        return []
    return [o.strip() for o in v.split(",") if o.strip()]


# instantiate settings
settings = Settings()

# expose module-level names for backward compatibility
CLOUDCAMPUS_BASE = settings.CLOUDCAMPUS_BASE
LOGIN_URL = f"{CLOUDCAMPUS_BASE}/login/index.php"
GRADE_URL_TEMPLATE = settings.GRADE_URL_TEMPLATE
MANUAL_MARK_URL = settings.MANUAL_MARK_URL

DEFAULT_COURSE_ID = settings.DEFAULT_COURSE_ID

ADMIN_USERNAME = settings.ADMIN_USERNAME
ADMIN_PASSWORD = settings.ADMIN_PASSWORD

DEFAULT_EXCLUDED_TASKS = _split_csv(settings.DEFAULT_EXCLUDED_TASKS)

CORS_ORIGINS = _split_csv(settings.CORS_ORIGINS)

RATE_LIMIT_LOGIN = settings.RATE_LIMIT_LOGIN
RATE_LIMIT_WINDOW = settings.RATE_LIMIT_WINDOW

PAYMENT_PID = settings.PAYMENT_PID
PAYMENT_KEY = settings.PAYMENT_KEY
PAYMENT_SITENAME = settings.PAYMENT_SITENAME
PAYMENT_BASE_PRICE = settings.PAYMENT_BASE_PRICE
PAYMENT_NOTIFY_PATH = settings.PAYMENT_NOTIFY_PATH
PAYMENT_RETURN_URL = settings.PAYMENT_RETURN_URL

TRUSTED_HOST = settings.TRUSTED_HOST

# zpay endpoints
ZPAY_API_URL = settings.ZPAY_API_URL
ZPAY_ORDER_QUERY_URL = settings.ZPAY_ORDER_QUERY_URL

CONTACT_EMAIL = settings.CONTACT_EMAIL
USER_AGENT = settings.USER_AGENT
