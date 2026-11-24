from config import get_config, save_config


def initialize_username():
    """初始化用户名"""
    conf = get_config()
    username = input("Enter your username: ")
    if 'user' not in conf:
        conf.add_section('user')
    conf['user']['username'] = username


def initialize_password():
    """初始化密码"""
    conf = get_config()
    password = input("Enter your password: ")
    if 'user' not in conf:
        conf.add_section('user')
    conf['user']['password'] = password


def initialize():
    """初始化所有配置"""
    conf = get_config()
    if 'target' not in conf:
        conf.add_section('target')
        conf['target']['course_shell'] = ''
    initialize_username()
    initialize_password()
    save_config()
    print("凭据已保存到 user_information.ini（该文件已被 .gitignore 忽略）")
