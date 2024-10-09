import re
import sys
import os
from core.widgets.base import BaseWidget
from core.validation.widgets.yasb.whkd import VALIDATION_SCHEMA
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QWidget, QApplication, QSizePolicy, QVBoxLayout, QScrollArea, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QIcon

class WhkdWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA

    def __init__(self, label: str, container_padding: dict):
        super().__init__(class_name="whkd-widget")
        self._label_content = label
        self._padding = container_padding
        # Construct container
        self._widget_container_layout: QHBoxLayout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(self._padding['left'],self._padding['top'],self._padding['right'],self._padding['bottom'])
        # Initialize container
        self._widget_container: QWidget = QWidget()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        # Add the container to the main widget layout
        self.widget_layout.addWidget(self._widget_container)
        self._create_dynamically_label(self._label_content)
        self._popup_window = None  # Initialize the popup window

    def _create_dynamically_label(self, content: str):
        def process_content(content, is_alt=False):
            label_parts = re.split('(<span.*?>.*?</span>)', content)
            label_parts = [part for part in label_parts if part]
            widgets = []
            for part in label_parts:
                part = part.strip()
                if not part:
                    continue
                if '<span' in part and '</span>' in part:
                    class_name = re.search(r'class=(["\'])([^"\']+?)\1', part)
                    class_result = class_name.group(2) if class_name else 'icon'
                    icon = re.sub(r'<span.*?>|</span>', '', part).strip()
                    label = QLabel(icon)
                    label.setProperty("class", class_result)
                    label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                else:
                    label = QLabel(part)
                    label.setProperty("class", "label")
                    label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._widget_container_layout.addWidget(label)
                widgets.append(label)
                label.show()
                label.mousePressEvent = self.show_popup
            return widgets
        self._widgets = process_content(content)

    def show_popup(self, event):
        # Check if WHKD_CONFIG_HOME exists in the environment variables
        whkd_config_home = os.getenv('WHKD_CONFIG_HOME')
        if whkd_config_home:
            file_path = os.path.join(whkd_config_home, 'whkdrc')
        else:
            file_path = os.path.join(os.path.expanduser('~'), '.config', 'whkdrc')

        filtered_lines = self.read_and_filter_file(file_path)
        formatted_content = self.format_content(filtered_lines)

        self._popup_window = KeybindsWindow(formatted_content, file_path)
        self._popup_window.show()

    def read_and_filter_file(self, file_path):
        with open(file_path, 'r') as file:
            lines = file.readlines()
        filtered_lines = []
        for line in lines:
            if not (line.strip().startswith('#') or line.strip().startswith('.shell')):
                # Remove inline comments
                line = line.split('#')[0].strip()
                if line:  # Only add non-empty lines
                    filtered_lines.append(line)
        return filtered_lines

    def format_content(self, lines):
        formatted_lines = []
        for line in lines:
            if ':' in line:
                keybind, command = line.split(':', 1)
                keybind = keybind.strip()
                command = command.strip()
                formatted_lines.append((keybind, command))
        return formatted_lines

class KeybindWidget(QWidget):
    def __init__(self, keybind, command):
        super().__init__()
        self.initUI(keybind, command)

    def initUI(self, keybind, command):
        layout = QHBoxLayout()
        
        keybind_label = QLabel(keybind)
        keybind_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keybind_label.setStyleSheet("background-color:#3a3a3a;color:white;padding:4px 8px;font-size:13px;min-width:120px;font-weight:bold;border-radius:4px;max-height:24px")
        command_label = QLabel(command)
        command_label.setStyleSheet("padding:4px;font-size: 14px")
        
        layout.addWidget(keybind_label)
        layout.addWidget(command_label)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 5)
        self.setLayout(layout)
        # Adjust the width of the keybind_label based on its content
        keybind_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        keybind_label.setMinimumWidth(keybind_label.sizeHint().width())

class KeybindsWindow(QWidget):
    def __init__(self, content, file_path):
        super().__init__()
        self.file_path = file_path
        self.initUI(content)

    def initUI(self, content):
        self.setWindowTitle('WHKD Keybinds')
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'assets', 'images', 'app_icon.png')
        icon = QIcon(icon_path)
        self.setWindowIcon(QIcon(icon.pixmap(48, 48)))
        # Get screen size and set window center
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        window_width = 640
        window_height = 640
        self.setGeometry(
            (screen_size.width() - window_width) // 2,
            (screen_size.height() - window_height) // 2,
            window_width,
            window_height
        )

        layout = QVBoxLayout()

        # Create a scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # Get the window's background color
        window_background_color = self.palette().color(self.backgroundRole()).name()
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {window_background_color};
                border: 0;
            }}
            QScrollBar:vertical {{
                background-color: {window_background_color};
                width: 4px;
                margin: 0px;
                border: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: #555;
                min-height: 20px;
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical {{
                height: 0;
            }}
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                border: 0;
                width: 0;
                height: 0;
                image: none;
                background: {window_background_color};
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

        # Create a widget to hold the keybind widgets
        container = QWidget()
        container_layout = QVBoxLayout()

        # Add each formatted line as a KeybindWidget
        for keybind, command in content:
            keybind_widget = KeybindWidget(keybind, command)
            container_layout.addWidget(keybind_widget)

        container.setLayout(container_layout)
        scroll_area.setWidget(container)

        layout.addWidget(scroll_area)

        # Add a button to open the file in the default text editor
        open_button = QPushButton("Edit Config File")
        open_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                background-color: #3a3a3a;
                color: white;
                border: 0;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0078D4;
            }
        """)
        open_button.clicked.connect(self.open_file)
        layout.addWidget(open_button)
        self.setLayout(layout)

    def open_file(self):
        os.startfile(self.file_path)
 