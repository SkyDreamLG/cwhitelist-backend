# utils/permissions.py
"""细粒度权限常量定义"""


class Permission:
    """API Token 权限字符串常量"""
    # 白名单
    WHITELIST_READ = "whitelist:read"
    WHITELIST_WRITE = "whitelist:write"
    WHITELIST_DELETE = "whitelist:delete"

    # 登录日志
    LOGIN_LOG = "login:log"

    # 超级权限
    FULL = "*:*"

    # ---- 预设组合 ----
    # 只读
    READ_ONLY = [WHITELIST_READ]

    # 服务器基础：同步白名单 + 记录登录
    SERVER_BASIC = [WHITELIST_READ, LOGIN_LOG]

    # 服务器完整：白名单增删查 + 登录日志
    SERVER_FULL = [WHITELIST_READ, WHITELIST_WRITE, WHITELIST_DELETE, LOGIN_LOG]

    @classmethod
    def all_permissions(cls):
        """所有独立权限列表"""
        return [
            cls.WHITELIST_READ,
            cls.WHITELIST_WRITE,
            cls.WHITELIST_DELETE,
            cls.LOGIN_LOG,
        ]

    @classmethod
    def get_label_key(cls, perm):
        """返回权限的翻译key，模板中使用 _(key) 获取翻译"""
        labels = _PERM_LABELS
        return labels.get(perm, perm)


# 显式列出所有翻译key，供pybabel提取
def _perm_labels_for_i18n():
    _("白名单-读取")
    _("白名单-写入")
    _("白名单-删除")
    _("登录日志-记录")
    _("超级权限")


_PERM_LABELS = {
    Permission.WHITELIST_READ: "白名单-读取",
    Permission.WHITELIST_WRITE: "白名单-写入",
    Permission.WHITELIST_DELETE: "白名单-删除",
    Permission.LOGIN_LOG: "登录日志-记录",
    Permission.FULL: "超级权限",
}
