from PySide6.QtWidgets import QMainWindow, QStackedWidget
from PySide6.QtCore import QSize
from services import ServiceContainer


class MainWindow(QMainWindow):
    def __init__(self, services: ServiceContainer):
        super().__init__()
        self._services = services
        self.setWindowTitle("Investments Terminal - Ailefroide")
        self.setMinimumSize(QSize(1000, 700))
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        from ui.pages.home_page import HomePage
        self.home_page = HomePage()
        self.stack.addWidget(self.home_page)
        self.liquid_page = None
        self.home_page.liquid_clicked.connect(self._show_liquid_page)

    def _show_liquid_page(self):
        if self.liquid_page is None:
            from ui.pages.liquid_page import LiquidPage
            self.liquid_page = LiquidPage(services=self._services)
            self.stack.addWidget(self.liquid_page)
            self.liquid_page.back_clicked.connect(self._show_home_page)
        self.stack.setCurrentIndex(1)

    def _show_home_page(self):
        self.stack.setCurrentIndex(0)


if __name__ == "__main__":
    from main import run
    run()
