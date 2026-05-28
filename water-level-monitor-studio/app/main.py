from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.cache import LocalCache
from app.config import AppConfig, ensure_dirs
from app.ui.login import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.style import APP_QSS


def main() -> int:
    ensure_dirs()
    config = AppConfig()
    app = QApplication(sys.argv)
    app.setApplicationName("Water Level Monitor Studio")
    app.setStyleSheet(APP_QSS)

    while True:
        login = LoginDialog(config)
        if login.exec() != LoginDialog.Accepted or not login.api:
            return 0

        try:
            cache = LocalCache(config.cache_path)
        except Exception as exc:
            QMessageBox.critical(None, "缓存初始化失败", str(exc))
            return 1

        window = MainWindow(login.api, cache, login.simulation_mode, role=login.role)
        window.show()
        app.exec()
        back_to_login = window.return_to_login
        window.deleteLater()
        if not back_to_login:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
