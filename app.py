#!/usr/bin/env python3
"""
CWhitelist 后端管理系统
"""

import os
import sys
from pathlib import Path
import threading
import webbrowser
import time


# 检查是否应该显示配置窗口
def show_config_window():
    """检查是否需要显示配置窗口"""
    # 如果有命令行参数，直接启动
    if len(sys.argv) > 1 and any(arg in sys.argv for arg in ['--no-gui', '--port']):
        return False

    # 检查环境变量
    if os.environ.get('CWHITELIST_NO_GUI') == '1':
        return False

    return True


# 如果显示配置窗口，导入tkinter
if show_config_window():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("警告: 无法导入tkinter，将使用默认配置")
        SHOW_CONFIG = False
    else:
        SHOW_CONFIG = True
else:
    SHOW_CONFIG = False

from flask import Flask, g, request, jsonify
from flask_login import LoginManager

# 创建应用实例
app = Flask(__name__)

# 加载配置
config_class = os.environ.get('FLASK_CONFIG', 'config.DevelopmentConfig')
app.config.from_object(config_class)

# 确保实例文件夹存在
instance_path = Path(app.instance_path)
instance_path.mkdir(exist_ok=True)

# 初始化数据库
from models.database import db

db.init_app(app)

# 初始化数据库迁移
from flask_migrate import Migrate

migrate = Migrate(app, db)

# 初始化登录管理器
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录以访问此页面'


# 用户加载函数
@login_manager.user_loader
def load_user(user_id):
    from models.user import User
    return User.query.get(int(user_id))


# 注册上下文处理器，使时区函数在模板中可用
@app.context_processor
def inject_timezone():
    from utils.timezone import (
        format_datetime,
        get_timezone_info,
        get_common_timezones,
        get_app_timezone,
        now_utc
    )
    return dict(
        format_datetime=format_datetime,
        timezone_info=get_timezone_info(),
        common_timezones=get_common_timezones(),
        current_timezone=str(get_app_timezone()),
        now_utc=now_utc
    )


# 在请求前设置时区
@app.before_request
def before_request():
    from utils.timezone import get_app_timezone
    g.timezone = get_app_timezone()
    g.timezone_str = str(g.timezone)


# 应用启动时初始化配置
def before_first_request():
    """第一次请求前初始化配置"""
    # 初始化文件夹
    folders = [
        app.config['UPLOAD_FOLDER'],
        os.path.dirname(app.config['LOG_FILE']),
        app.instance_path
    ]

    for folder in folders:
        Path(folder).mkdir(parents=True, exist_ok=True)

    # 从数据库加载时区设置
    try:
        from models.setting import Setting
        from models.database import db

        # 检查数据库连接
        with app.app_context():
            # 确保表存在
            db.create_all()

            # 从数据库获取时区设置，如果存在则覆盖配置
            timezone_setting = Setting.query.filter_by(key='timezone').first()
            if timezone_setting and timezone_setting.value:
                app.config['TIMEZONE'] = timezone_setting.value
                print(f"✓ 已从数据库加载时区设置: {timezone_setting.value}")
            else:
                # 保存默认时区到数据库
                Setting.set_value('timezone', app.config['TIMEZONE'], '系统时区设置', 'system')
                print(f"✓ 已保存默认时区到数据库: {app.config['TIMEZONE']}")
    except Exception as e:
        print(f"⚠ 加载数据库时区设置失败: {e}")
        print(f"  使用配置时区: {app.config['TIMEZONE']}")


# 添加时区刷新端点（用于AJAX更新）
@app.route('/api/timezone/refresh')
def refresh_timezone():
    """刷新时区设置"""
    from utils.timezone import get_timezone_info
    try:
        info = get_timezone_info()
        return jsonify({
            'success': True,
            'timezone_info': info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


# 注册蓝图
from routes.auth import auth_bp
from routes.api import api_bp
from routes.web import web_bp

# 确保只注册一次
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(web_bp, url_prefix='/')


def run_flask(host='0.0.0.0', port=5000, debug=False):
    """运行Flask应用"""
    with app.app_context():
        db.create_all()
        print("数据库表已创建完成")

        # 检查是否需要OOBE
        from routes.web import is_oobe_required

        if is_oobe_required():
            print("\n⚠  系统需要初始设置")
            print(f"请访问: http://localhost:{port}/oobe")
        else:
            print("✓ 系统已初始化")

        print(f"时区设置: {app.config.get('TIMEZONE', 'UTC')}")
        print(f"服务器地址: http://{host}:{port}")
        print("按 Ctrl+C 停止服务器\n")

    app.run(host=host, port=port, debug=debug)


class ConfigWindow:
    """配置窗口"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CWhitelist 服务器配置")
        self.root.geometry("800x600")
        self.root.resizable(False, False)

        # 居中显示
        self.center_window()

        # 设置窗口图标（如果有的话）
        try:
            self.root.iconbitmap('icon.ico')
        except:
            pass

        self.setup_ui()
        self.server_thread = None

    def center_window(self):
        """窗口居中"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def setup_ui(self):
        """设置UI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="CWhitelist 服务器配置",
                                font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))

        # 配置框架
        config_frame = ttk.LabelFrame(main_frame, text="服务器设置", padding="15")
        config_frame.pack(fill=tk.X, pady=(0, 15))

        # 主机地址
        host_frame = ttk.Frame(config_frame)
        host_frame.pack(fill=tk.X, pady=8)

        ttk.Label(host_frame, text="监听地址:", width=12).pack(side=tk.LEFT)
        host_combo = ttk.Combobox(host_frame, width=25,
                                  values=["0.0.0.0", "127.0.0.1", "localhost"])
        host_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.host_var = tk.StringVar(value="0.0.0.0")
        host_combo.config(textvariable=self.host_var)

        # 地址说明标签
        host_help_label = ttk.Label(host_frame, text="", foreground="blue", font=("Arial", 9))
        host_help_label.pack(side=tk.LEFT, padx=(10, 0))

        # 地址选择事件处理
        def on_host_selected(event):
            host = self.host_var.get()
            if host == "0.0.0.0":
                host_help_label.config(text="所有网络可访问", foreground="green")
            elif host == "127.0.0.1":
                host_help_label.config(text="仅本机访问", foreground="orange")
            elif host == "localhost":
                host_help_label.config(text="本机访问", foreground="blue")

        host_combo.bind('<<ComboboxSelected>>', on_host_selected)
        host_combo.bind('<KeyRelease>', on_host_selected)

        # 初始化显示
        on_host_selected(None)

        # 端口设置
        port_frame = ttk.Frame(config_frame)
        port_frame.pack(fill=tk.X, pady=8)

        ttk.Label(port_frame, text="监听端口:", width=12).pack(side=tk.LEFT)
        port_entry = ttk.Entry(port_frame, width=28)
        port_entry.pack(side=tk.LEFT, padx=(5, 0))
        self.port_var = tk.StringVar(value="5000")
        port_entry.config(textvariable=self.port_var)

        # 端口验证
        def validate_port(value):
            if value == "":
                return True
            try:
                port = int(value)
                return 1 <= port <= 65535
            except:
                return False

        vcmd = (self.root.register(validate_port), '%P')
        port_entry.config(validate="key", validatecommand=vcmd)

        # 端口说明标签
        port_help_label = ttk.Label(port_frame, text="(1-65535)", foreground="gray", font=("Arial", 9))
        port_help_label.pack(side=tk.LEFT, padx=(10, 0))

        # 浏览器选项
        browser_frame = ttk.Frame(config_frame)
        browser_frame.pack(fill=tk.X, pady=8)

        self.open_browser_var = tk.BooleanVar(value=True)
        browser_check = ttk.Checkbutton(browser_frame, text="启动后自动打开浏览器",
                                        variable=self.open_browser_var)
        browser_check.pack(side=tk.LEFT)

        # 浏览器说明标签
        browser_help_label = ttk.Label(browser_frame, text="将自动访问管理界面",
                                       foreground="gray", font=("Arial", 9))
        browser_help_label.pack(side=tk.LEFT, padx=(10, 0))

        # 地址说明区域
        address_info_frame = ttk.LabelFrame(main_frame, text="地址说明", padding="10")
        address_info_frame.pack(fill=tk.X, pady=(0, 15))

        # 创建说明文本
        info_text = """• 0.0.0.0 - 所有网络可访问 (局域网/外网均可)
• 127.0.0.1 - 仅本机访问 (更安全)
• localhost - 本机访问 (与127.0.0.1类似)

默认端口 5000 如果被占用，可尝试 8080、8000、5001 等"""

        info_label = ttk.Label(address_info_frame, text=info_text, justify=tk.LEFT,
                               foreground="#666666", font=("Arial", 9))
        info_label.pack(anchor=tk.W)

        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        # 左对齐的按钮
        left_button_frame = ttk.Frame(button_frame)
        left_button_frame.pack(side=tk.LEFT)

        # 默认值按钮
        default_btn = ttk.Button(left_button_frame, text="恢复默认值",
                                 command=self.set_default_values)
        default_btn.pack(side=tk.LEFT, padx=(0, 5))

        # 右对齐的按钮
        right_button_frame = ttk.Frame(button_frame)
        right_button_frame.pack(side=tk.RIGHT)

        # 取消按钮
        cancel_btn = ttk.Button(right_button_frame, text="取消",
                                command=self.root.quit)
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))

        # 确认按钮
        confirm_btn = ttk.Button(right_button_frame, text="启动服务器",
                                 command=self.start_server, style="Accent.TButton")
        confirm_btn.pack(side=tk.RIGHT)

        # 设置样式
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 10, "bold"), padding=8)

        # 绑定回车键
        self.root.bind('<Return>', lambda e: self.start_server())
        port_entry.focus_set()

        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """窗口关闭时的处理"""
        if self.server_thread and self.server_thread.is_alive():
            response = messagebox.askyesno("确认", "服务器仍在运行，确定要退出吗？")
            if response:
                print("\n服务器正在停止...")
                # 这里可以添加停止服务器的逻辑
                self.root.quit()
        else:
            self.root.quit()

    def set_default_values(self):
        """恢复默认值"""
        self.host_var.set("0.0.0.0")
        self.port_var.set("5000")
        self.open_browser_var.set(True)

        # 触发地址说明更新
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Combobox):
                widget.event_generate('<<ComboboxSelected>>')
                break

    def start_server(self):
        """启动服务器"""
        try:
            port = int(self.port_var.get())
            if not (1 <= port <= 65535):
                messagebox.showerror("错误", "端口号必须在 1-65535 之间")
                return
        except ValueError:
            messagebox.showerror("错误", "请输入有效的端口号")
            return

        host = self.host_var.get()
        open_browser = self.open_browser_var.get()

        # 检查端口是否被占用
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.close()
        except socket.error:
            response = messagebox.askyesno("端口被占用",
                                           f"端口 {port} 可能已被占用，是否尝试其他端口？\n\n"
                                           f"建议尝试: {port + 1}, 8080, 8000")

            if response:
                # 用户选择尝试其他端口
                self.port_var.set(str(port + 1))
                self.root.focus_force()
                return
            else:
                # 用户选择继续
                pass

        # 显示确认对话框
        confirm_msg = f"确认启动服务器？\n\n"
        confirm_msg += f"监听地址: {host}\n"
        confirm_msg += f"监听端口: {port}\n"
        confirm_msg += f"自动打开浏览器: {'是' if open_browser else '否'}\n\n"

        if host == "0.0.0.0":
            confirm_msg += "⚠ 注意: 所有网络均可访问服务器"

        result = messagebox.askyesno("确认启动", confirm_msg)
        if not result:
            return

        # 显示启动信息
        messagebox.showinfo("启动中", f"服务器正在启动...\n\n"
                                      f"地址: {host}:{port}\n"
                                      f"配置窗口将关闭，服务器在后台运行。")

        # 在新线程中启动Flask服务器
        def run_server():
            # 延迟打开浏览器
            if open_browser:
                def open_browser_delayed():
                    try:
                        url = f"http://127.0.0.1:{port}"
                        if host == "127.0.0.1" or host == "localhost":
                            url = f"http://{host}:{port}"
                        webbrowser.open(url)
                        print(f"✓ 已自动打开浏览器: {url}")
                    except Exception as e:
                        print(f"⚠ 无法自动打开浏览器: {e}")

                timer = threading.Timer(2.0, open_browser_delayed)
                timer.daemon = True
                timer.start()

            # 运行Flask应用
            run_flask(host=host, port=port, debug=False)

        # 启动服务器线程
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        # 关闭配置窗口，但保持程序运行
        self.root.destroy()

    def run(self):
        """运行配置窗口"""
        self.root.mainloop()


def run_server_directly(host='0.0.0.0', port=5000, debug=False):
    """直接运行服务器（不使用GUI）"""
    run_flask(host=host, port=port, debug=debug)


def main():
    """主函数"""
    print("=" * 50)
    print("CWhitelist 后端管理系统")
    print("=" * 50)

    # 检查命令行参数
    if len(sys.argv) > 1:
        # 处理命令行参数
        import argparse
        parser = argparse.ArgumentParser(description='CWhitelist 后端管理系统')
        parser.add_argument('--port', type=int, default=5000, help='监听端口')
        parser.add_argument('--host', default='0.0.0.0', help='监听地址')
        parser.add_argument('--no-gui', action='store_true', help='不使用GUI界面')
        parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
        parser.add_argument('--debug', action='store_true', help='调试模式')

        args = parser.parse_args()

        # 如果使用GUI模式且有浏览器选项
        if not args.no_gui and SHOW_CONFIG:
            print("使用GUI配置界面...")
            try:
                window = ConfigWindow()
                window.run()
                # 窗口关闭后，检查是否启动了服务器线程
                if window.server_thread and window.server_thread.is_alive():
                    # 等待服务器线程
                    window.server_thread.join()
            except Exception as e:
                print(f"GUI启动失败: {e}")
                print("将使用命令行配置启动...")
                run_server_directly(host=args.host, port=args.port, debug=args.debug)
        else:
            # 直接启动Flask
            run_server_directly(host=args.host, port=args.port, debug=args.debug)
    elif SHOW_CONFIG:
        # 显示配置窗口
        try:
            window = ConfigWindow()
            window.run()
            # 窗口关闭后，检查是否启动了服务器线程
            if window.server_thread and window.server_thread.is_alive():
                # 等待服务器线程
                window.server_thread.join()
        except Exception as e:
            print(f"配置窗口启动失败: {e}")
            print("将使用默认配置启动...")
            run_server_directly()
    else:
        # 直接启动
        run_server_directly()


if __name__ == '__main__':
    main()