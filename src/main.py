import sys
from PyQt5.QtWidgets import QApplication
from qt_material import apply_stylesheet
from src.ui.main_window import SubtitleProcessor


def main():
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="dark_teal.xml")
    processor = SubtitleProcessor()
    processor.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
