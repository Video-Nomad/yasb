import re
import logging
import subprocess
from typing import Optional
from core.widgets.base import BaseWidget
from core.validation.widgets.komorebi.control import VALIDATION_SCHEMA
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QThread
from core.utils.utilities import PopupWidget
from core.utils.widgets.animation_manager import AnimationManager
from core.event_service import EventService
from core.event_enums import KomorebiEvent
from core.utils.komorebi.client import KomorebiClient

class KomorebiControlWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA

    k_signal_connect = pyqtSignal(dict)
    k_signal_disconnect = pyqtSignal()

    def __init__(
            self,
            label: str,
            icons: dict[str, str],
            run_ahk: bool,
            run_whkd: bool,
            show_version: bool,
            komorebi_menu: dict[str, str],
            container_padding: dict[str, int],
            animation: dict[str, str],
            callbacks: dict[str, str],
    ):
        super().__init__(class_name="komorebi-control-widget")

        self._label_content = label
        self._icons = icons
        self._run_ahk = run_ahk
        self._run_whkd = run_whkd
        self._show_version = show_version
        self._komorebi_menu = komorebi_menu
        self._animation = animation
        self._padding = container_padding
        self._is_komorebi_connected = False
        self._locked_ui = False
        self._version_text = None

        # Initialize the event service
        self._event_service = EventService()
        self._komorebic = KomorebiClient()

        # Construct container
        self._widget_container_layout: QHBoxLayout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(self._padding['left'], self._padding['top'], self._padding['right'], self._padding['bottom'])
        # Initialize container
        self._widget_container: QWidget = QWidget()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        # Add the container to the main widget layout
        self.widget_layout.addWidget(self._widget_container)

        self._create_dynamically_label(self._label_content)

        self.register_callback("toggle_menu", self._toggle_menu)

        self.callback_left = callbacks['on_left']
        self.callback_right = callbacks['on_right']
        self.callback_middle = callbacks['on_middle']

        # Register events
        self._register_signals_and_events()

    def _register_signals_and_events(self):
        # Connect signals to handlers
        self.k_signal_connect.connect(self._on_komorebi_connect_event)
        self.k_signal_disconnect.connect(self._on_komorebi_disconnect_event)
        # Register for events
        self._event_service.register_event(KomorebiEvent.KomorebiConnect, self.k_signal_connect)
        self._event_service.register_event(KomorebiEvent.KomorebiDisconnect, self.k_signal_disconnect)

    def _start_version_check(self):
        """Starts a background thread to retrieve the Komorebi version."""
        self._version_thread = VersionCheckThread(self._komorebic)
        self._version_thread.version_result.connect(self._on_version_result)
        self._version_thread.start()

    def _on_version_result(self, version):
        """Receives the Komorebi version from the thread and updates the UI."""
        self._version_text = f"komorebi v{version}" if version else None
        if getattr(self, 'dialog', None) and self.dialog.isVisible():
            self._update_menu_button_states()
            # Update the version label in the currently open dialog
            for child in self.dialog.findChildren(QLabel):
                if child.property("class") == "text version":
                    child.setText(self._version_text)
                    break

    def _toggle_menu(self):
        if self._animation['enabled']:
            AnimationManager.animate(
                self, self._animation['type'], self._animation['duration'])
        self.show_menu()

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
                    class_result = class_name.group(
                        2) if class_name else 'icon'
                    icon = re.sub(r'<span.*?>|</span>', '', part).strip()
                    label = QLabel(icon)
                    label.setProperty("class", class_result)
                else:
                    label = QLabel(part)
                    label.setProperty("class", "label")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                self._widget_container_layout.addWidget(label)
                widgets.append(label)
                label.show()
            return widgets
        self._widgets = process_content(content)

    def show_menu(self):
        if self._version_text is None:
            # If we don't have a version yet, start an async check
            self._start_version_check()
        # Always create a fresh dialog
        self.dialog = PopupWidget(self, self._komorebi_menu['blur'], self._komorebi_menu['round_corners'],
                                  self._komorebi_menu['round_corners_type'], self._komorebi_menu['border_color'])
        self.dialog.setProperty("class", "komorebi-control-menu")
        self.dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.dialog.setWindowFlag(Qt.WindowType.Popup)
        self.dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # Top row with buttons
        buttons_row = QWidget()
        buttons_layout = QHBoxLayout(buttons_row)
        buttons_layout.setContentsMargins(10, 10, 10, 10)
        buttons_layout.setSpacing(5)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Store buttons as class attributes so we can update them
        self.start_btn = QLabel(self._icons['start'])
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.stop_btn = QLabel(self._icons['stop'])
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.reload_btn = QLabel(self._icons['reload'])
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Connect button click events
        self.start_btn.mousePressEvent = lambda e: self._start_komorebi()
        self.stop_btn.mousePressEvent = lambda e: self._stop_komorebi()
        self.reload_btn.mousePressEvent = lambda e: self._reload_komorebi()

        # Update the button states based on current connection status
        self._update_menu_button_states()

        buttons_layout.addWidget(self.start_btn)
        buttons_layout.addWidget(self.stop_btn)
        buttons_layout.addWidget(self.reload_btn)

        # Bottom row with version info
        version_row = QWidget()
        version_row.setProperty("class", "footer")
        version_layout = QVBoxLayout(version_row)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(0)
        version_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version_label = QLabel(self._version_text)
        version_label.setProperty("class", "text version")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        version_layout.addWidget(version_label)

        # Add widgets to main layout vertically
        layout.addWidget(buttons_row)
        if self._show_version:
            layout.addWidget(version_row)

        self.dialog.setLayout(layout)

        # Position the dialog
        self.dialog.adjustSize()
        widget_global_pos = self.mapToGlobal(QPoint(
            self._komorebi_menu['offset_left'], self.height() + self._komorebi_menu['offset_top']))
        if self._komorebi_menu['direction'] == 'up':
            global_y = self.mapToGlobal(QPoint(0, 0)).y(
            ) - self.dialog.height() - self._komorebi_menu['offset_left']
            widget_global_pos = QPoint(self.mapToGlobal(
                QPoint(0, 0)).x() + self._komorebi_menu['offset_left'], global_y)

        if self._komorebi_menu['alignment'] == 'left':
            global_position = widget_global_pos
        elif self._komorebi_menu['alignment'] == 'right':
            global_position = QPoint(
                widget_global_pos.x() + self.width() - self.dialog.width(),
                widget_global_pos.y()
            )
        elif self._komorebi_menu['alignment'] == 'center':
            global_position = QPoint(
                widget_global_pos.x() + (self.width() - self.dialog.width()) // 2,
                widget_global_pos.y()
            )
        else:
            global_position = widget_global_pos

        self.dialog.move(global_position)

        self.dialog.show()

    def _on_komorebi_connect_event(self) -> None:
        self._is_komorebi_connected = True
        self._locked_ui = False
        # Clear the reloading flag if it exists
        if hasattr(self, '_is_reloading'):
            self._is_reloading = False

        try:
            self._update_menu_button_states()
        except:
            pass

    def _on_komorebi_disconnect_event(self) -> None:
        self._is_komorebi_connected = False
        # Only unlock UI if this isn't part of a reload operation
        if not hasattr(self, '_is_reloading') or not self._is_reloading:
            self._locked_ui = False

        try:
            self._update_menu_button_states()
        except:
            pass  # Dialog may have been deleted
        # No need to directly update the UI if dialog isn't visible

    def _update_menu_button_states(self):
        # Check if buttons should be disabled
        disable_buttons = (
            self._locked_ui or
            self._version_text is None
        )

        self.start_btn.setDisabled(disable_buttons)
        self.stop_btn.setDisabled(disable_buttons)
        self.reload_btn.setDisabled(disable_buttons)

        # Update the button classes
        if self._is_komorebi_connected:
            self.start_btn.setProperty("class", "button start")
            self.stop_btn.setProperty("class", "button stop active")
            self.reload_btn.setProperty("class", "button reload")
        else:
            self.start_btn.setProperty("class", "button start active")
            self.stop_btn.setProperty("class", "button stop")
            self.reload_btn.setProperty("class", "button reload")

        # Force style refresh on each button
        for btn in (self.start_btn, self.stop_btn, self.reload_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _run_komorebi_command(self, command: str):
        """Runs a Komorebi command with locked UI and error handling."""
        self._locked_ui = True
        self._update_menu_button_states()
        try:
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            self._locked_ui = False
            logging.error(f"Error running '{command}': {e}")

    def _build_komorebi_flags(self) -> str:
        """Build command line flags based on configuration."""
        flags = []
        if self._run_whkd:
            flags.append("--whkd")
        if self._run_ahk:
            flags.append("--ahk")
        return " ".join(flags)

    def _start_komorebi(self):
        if not self._is_komorebi_connected:
            flags = self._build_komorebi_flags()
            command = f"{self._komorebic._komorebic_path} start {flags}"
            self._run_komorebi_command(command)

    def _stop_komorebi(self):
        if self._is_komorebi_connected:
            flags = self._build_komorebi_flags()
            command = f"{self._komorebic._komorebic_path} stop {flags}"
            self._run_komorebi_command(command)

    def _reload_komorebi(self):
        if self._is_komorebi_connected:
            self._is_reloading = True
            flags = self._build_komorebi_flags()
            command = (
                f"{self._komorebic._komorebic_path} stop {flags} "
                f"&& {self._komorebic._komorebic_path} start {flags}"
            )
            try:
                self._run_komorebi_command(command)
            except Exception as e:
                self._is_reloading = False
                self._locked_ui = False
                logging.error(f"Error reloading Komorebi: {e}")

class VersionCheckThread(QThread):
    version_result = pyqtSignal(str)

    def __init__(self, komorebic_client):
        super().__init__()
        self._komorebic = komorebic_client

    def run(self):
        version = self.get_version()
        self.version_result.emit(version if version else None)

    def get_version(self) -> Optional[str]:
        """Returns the Komorebi version or None if unavailable."""
        try:
            output = subprocess.check_output(
                [self._komorebic._komorebic_path, "--version"],
                timeout=self._komorebic._timeout_secs,
                stderr=subprocess.STDOUT,
                shell=True,
                text=True,
            )
            match = re.search(r'komorebic\s+(\d+\.\d+\.\d+)',
                              output.strip().split('\n')[0])
            return match.group(1) if match else None
        except:
            return None