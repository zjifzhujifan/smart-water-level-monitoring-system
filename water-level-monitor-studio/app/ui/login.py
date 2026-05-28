from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.api_client import ApiError, WaterMonitorApi
from app.config import AppConfig


class LoginDialog(QDialog):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.setObjectName("LoginDialog")
        self.setWindowTitle("Water Level Monitor Studio - 登录")
        self.setFixedSize(800, 330)
        self.api: WaterMonitorApi | None = None
        self.simulation_mode = False
        self.role = "admin"

        title = QLabel("水位监测桌面控制台")
        title.setObjectName("LoginTitle")
        subtitle = QLabel("连接现有 Spring Boot 后端，或进入离线演示模式")
        subtitle.setObjectName("LoginSubTitle")

        intro = QFrame()
        intro.setObjectName("LoginIntro")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(0, 0, 0, 0)
        intro_layout.setSpacing(12)
        intro_layout.addWidget(title)
        intro_layout.addWidget(subtitle)
        intro_hint = QLabel("支持后端联调、离线演示和不同角色权限入口")
        intro_hint.setObjectName("LoginHint")
        intro_hint.setWordWrap(True)
        intro_layout.addSpacing(24)
        intro_layout.addWidget(intro_hint)
        intro_layout.addStretch()

        self.server = QLineEdit(config.api_base_url)
        self.username = QLineEdit(config.default_username)
        self.password = QLineEdit(config.default_password)
        self.password.setEchoMode(QLineEdit.Password)
        for field in (self.server, self.username, self.password):
            field.setObjectName("LoginField")
            field.setFixedSize(300, 36)

        self.offline = QCheckBox("离线演示模式")
        self.offline.setObjectName("LoginCheck")

        self.role_group = QButtonGroup(self)
        self.role_group.setExclusive(True)
        role_row = QFrame()
        role_row.setObjectName("RoleRow")
        role_row.setFixedSize(300, 36)
        role_layout = QHBoxLayout(role_row)
        role_layout.setContentsMargins(0, 0, 0, 0)
        role_layout.setSpacing(6)
        for index, (label, value) in enumerate((("管理员", "admin"), ("调试员", "debugger"), ("访客", "viewer"))):
            button = QPushButton(label)
            button.setObjectName("RoleButton")
            button.setCheckable(True)
            button.setProperty("role", value)
            button.setFixedSize(96, 36)
            self.role_group.addButton(button)
            role_layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        form_panel = QFrame()
        form_panel.setObjectName("LoginForm")
        form_panel.setFixedHeight(212)
        form = QFormLayout(form_panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("后端地址", self.server)
        form.addRow("用户名", self.username)
        form.addRow("密码", self.password)
        form.addRow("角色", role_row)
        form.addRow("", self.offline)

        self.login_btn = QPushButton("登录")
        self.login_btn.setObjectName("Primary")
        self.cancel_btn = QPushButton("取消")
        self.login_btn.setFixedSize(88, 36)
        self.cancel_btn.setFixedSize(88, 36)
        self.login_btn.clicked.connect(self.do_login)
        self.cancel_btn.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.login_btn)

        right = QFrame()
        right.setObjectName("LoginRight")
        right.setFixedWidth(400)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(form_panel)
        right_layout.addLayout(actions)
        right_layout.addStretch()

        shell = QFrame()
        shell.setObjectName("LoginShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(26, 26, 26, 24)
        shell_layout.setSpacing(24)
        shell_layout.addWidget(intro, 1)
        shell_layout.addWidget(right, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(shell)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

    def selected_role(self) -> str:
        button = self.role_group.checkedButton()
        return str(button.property("role")) if button else "admin"

    def do_login(self) -> None:
        if self.offline.isChecked():
            self.simulation_mode = True
            self.role = self.selected_role()
            self.api = WaterMonitorApi(self.server.text().strip())
            self.accept()
            return
        api = WaterMonitorApi(self.server.text().strip())
        try:
            api.login(self.username.text().strip(), self.password.text())
        except ApiError as exc:
            QMessageBox.warning(self, "登录失败", str(exc))
            return
        self.api = api
        self.simulation_mode = False
        self.role = self.selected_role()
        self.accept()
