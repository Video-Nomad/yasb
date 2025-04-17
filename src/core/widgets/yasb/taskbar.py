import logging
import time
import atexit
from typing import Optional

from PIL import Image
import win32gui
import win32con

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QImage, QCursor
from PySide6.QtWidgets import QLabel, QHBoxLayout, QWidget, QGraphicsOpacityEffect, QApplication

from settings import DEBUG
from core.widgets.base import BaseWidget
from core.utils.win32.windows import WinEvent
from core.event_service import EventService
from core.validation.widgets.yasb.taskbar import VALIDATION_SCHEMA
from core.utils.win32.utilities import get_hwnd_info
from core.utils.win32.app_icons import get_window_icon
from core.utils.widgets.animation_manager import AnimationManager

try:
    from core.utils.win32.event_listener import SystemEventListener
except ImportError:
    SystemEventListener = None
    logging.warning("Failed to load Win32 System Event Listener")
    
# Missing from win32con
WS_EX_NOREDIRECTIONBITMAP = 0x20_0000

# Exclude the context menu, taskbar, and other system classes that we don't want to process
EXCLUDED_CLASSES = {
    "Progman",
    "SysListView32",
    "XamlExplorerHostIslandWindow_WASDK",
    "Microsoft.UI.Content.PopupWindowSiteBridge",
    "Microsoft.UI.Content.DesktopChildSiteBridge",
    "Windows.UI.Composition.DesktopWindowContentBridge",
    "SysHeader32",
    "Windows.UI.Input.InputSite.WindowClass",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "#32768",
    "Qt673QWindowToolSaveBits",
    "Qt673QWindowToolTipSaveBits",
    "Qt673QWindowToolTipDropShadowSaveBits"
}

class TaskbarWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA
    update_event = Signal(int, WinEvent)
    event_listener = SystemEventListener

    def __init__(
            self,
            icon_size: int,
            animation:dict[str, str] | bool,
            title_label: dict[str, str],
            tooltip: bool,
            ignore_apps: dict[str, list[str]],
            container_padding: dict,
            callbacks: dict[str, str]
    ):
        super().__init__(class_name="taskbar-widget")

        self.dpi = None # Initial DPI value
        self.icon_label = QLabel()
        self._label_icon_size = icon_size
        if isinstance(animation, bool):
            # Default animation settings if only a boolean is provided to prevent breaking configurations
            self._animation = {
                'enabled': animation,
                'type': 'fadeInOut',
                'duration': 200
            }
        else:
            self._animation = animation
        self._title_label = title_label
        self._tooltip = tooltip
        self._ignore_apps = ignore_apps
        self._padding = container_padding
        self._win_info = None
        self._update_retry_count = 0

        self._icon_cache = dict()
        self._window_buttons = {}
        self._hwnd_title_cache = {}
        self._event_service = EventService()
        
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
        
        self.register_callback("toggle_window", self._on_toggle_window)
        self.register_callback("close_app", self._on_close_app)
        self.callback_left = callbacks["on_left"]
        self.callback_right = callbacks["on_right"]
        self.callback_middle = callbacks["on_middle"]
        
        self.update_event.connect(self._process_event)
        self._event_service.register_event(WinEvent.EventSystemForeground, self.update_event)
        self._event_service.register_event(WinEvent.EventObjectFocus, self.update_event)
        self._event_service.register_event(WinEvent.EventObjectHide, self.update_event)
        
        if self._tooltip or self._title_label['enabled']:
            # Register for title change events only if title labels or tooltip are enabled
            self._event_service.register_event(WinEvent.EventObjectNameChange, self.update_event)
        self._event_service.register_event(WinEvent.EventObjectDestroy, self.update_event)
        
        # Load all currently visible windows when the widget is initialized
        self._load_initial_windows()
        
        if QApplication.instance():
            QApplication.instance().aboutToQuit.connect(self._stop_events)
        atexit.register(self._stop_events)


    def _stop_events(self) -> None:
        self._event_service.clear()
 
    def _on_close_app(self) -> None:
        widget = QApplication.instance().widgetAt(QCursor.pos())
        if not widget:
            logging.warning("No widget found under cursor.")
            return
        
        hwnd = widget.property("hwnd")
        if not hwnd:
            logging.warning("No hwnd found for widget.")
            return

        # Check if the window is valid before attempting to close it
        if win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        else:
            logging.warning(f"Invalid window handle: {hwnd}")

    def _process_event(self, hwnd: int, event: WinEvent) -> None:
        # Maintain a dictionary of last event times per (hwnd, event)
        if not hasattr(self, "_last_event_time"):
            self._last_event_time = {}
        now = time.time()
        key = (hwnd, event)
        debounce_interval = 0.1  # seconds
        if now - self._last_event_time.get(key, 0) < debounce_interval:
            return  # Skip event
        self._last_event_time[key] = now

        win_info = get_hwnd_info(hwnd)
        if (not win_info or not hwnd or
                not win_info['title'] or
                win_info['class_name'] in EXCLUDED_CLASSES or
                win_info['title'] in self._ignore_apps['titles'] or
                win_info['class_name'] in self._ignore_apps['classes'] or
                win_info['process']['name'] in self._ignore_apps['processes']):
            return

        cached_title = self._hwnd_title_cache.get(hwnd)
        # For EventObjectNameChange, if the title hasn't changed, just ignore.
        if self._tooltip or self._title_label['enabled']:
            if event == WinEvent.EventObjectNameChange and win_info['title'] == cached_title:
                return

        if win_info['title'] != cached_title or event != WinEvent.EventSystemForeground:
            self._hwnd_title_cache[hwnd] = win_info['title']
            self._update_label(hwnd, event)
 

    def _update_label(self, hwnd: int, event: WinEvent) -> None:
        visible_windows = self.get_visible_windows(hwnd, event)
        existing_hwnds = set(self._window_buttons.keys())
        new_icons = []
        removed_hwnds = []
        updated_titles = {}

        for title, hwnd, icon, process in visible_windows:
            if hwnd not in self._window_buttons and icon is not None:
                self._window_buttons[hwnd] = (title, icon, hwnd, process)
                new_icons.append((title, icon, hwnd, process))
            elif hwnd in existing_hwnds:
                existing_hwnds.remove(hwnd)
                old_title = self._window_buttons[hwnd][0]
                if old_title != title:
                    # Update the stored title in window_buttons
                    self._window_buttons[hwnd] = (title, self._window_buttons[hwnd][1], hwnd, process)
                    updated_titles[hwnd] = title

        # Collect hwnds for windows that are no longer visible
        for hwnd in existing_hwnds:
            removed_hwnds.append(hwnd)
            del self._window_buttons[hwnd]

        # Remove icons for windows that are no longer visible
        for i in reversed(range(self._widget_container_layout.count())):
            widget = self._widget_container_layout.itemAt(i).widget()
            hwnd = widget.property("hwnd")

            if self._title_label['enabled']:
                if widget.property("class") and "app-title" in str(widget.property("class")):
                    if hwnd in removed_hwnds:
                        # Remove title labels for closed windows
                        self._widget_container_layout.removeWidget(widget)
                        widget.deleteLater()
                    elif hwnd in self._window_buttons:
                        title = self._window_buttons[hwnd][0]
                        formatted_title = self._format_title(title)
                        if widget.text() != formatted_title:
                            widget.setText(formatted_title)
                            
                        widget.setProperty("class", self._get_title_class(hwnd))
                        if self._title_label['show'] == 'focused':
                            widget.setVisible(self._get_title_visibility(hwnd))
                        widget.style().unpolish(widget)
                        widget.style().polish(widget)
                    continue  # Skip the rest of the loop for title labels
                

            widget.setProperty("class", self._get_icon_class(hwnd))
            widget.style().unpolish(widget)
            widget.style().polish(widget)

            # Update tooltip if title changed and tooltip is enabled
            if self._tooltip and hwnd in updated_titles:
                title = updated_titles[hwnd]
                widget.setToolTip(self._format_title(title))

            if widget != self.icon_label:
                if hwnd in removed_hwnds:
                    if self._animation['enabled']:
                        self._animate_icon(widget, start_width=widget.width(), end_width=0)
                    else:
                        self._widget_container_layout.removeWidget(widget)
                        widget.deleteLater()

        # Add new icons
        for title, icon, hwnd, process in new_icons:
            icon_label = QLabel()
            icon_label.setProperty("class", self._get_icon_class(hwnd))
            if self._animation['enabled']:
                icon_label.setFixedWidth(0)
            icon_label.setPixmap(icon)
            if self._tooltip:
                icon_label.setToolTip(self._format_title(title))
            icon_label.setProperty("hwnd", hwnd)
            icon_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self._widget_container_layout.addWidget(icon_label)

            if self._title_label['enabled']:    
                title_label = QLabel(self._format_title(title))
                title_label.setProperty("class", self._get_title_class(hwnd))
                title_label.setProperty("hwnd", hwnd)
                title_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                if self._tooltip:
                    title_label.setToolTip(self._format_title(title))
                self._widget_container_layout.addWidget(title_label)
                if self._title_label['show'] == 'focused':
                    title_label.setVisible(self._get_title_visibility(hwnd))

            if self._animation['enabled']:
                self._animate_icon(icon_label, start_width=0, end_width=icon_label.sizeHint().width())



    def _get_icon_class(self, hwnd: int) -> str:
        if hwnd == win32gui.GetForegroundWindow():
            return "app-icon foreground"
        return "app-icon"

    def _get_title_class(self, hwnd: int) -> str:
        if hwnd == win32gui.GetForegroundWindow():
            return "app-title foreground"
        return "app-title"
    
    def _get_title_visibility(self, hwnd: int) -> str:
        if hwnd == win32gui.GetForegroundWindow():
            return True
        return False
 
    def _format_title(self, title: str) -> str:
        """Format a window title according to max and min length settings."""
        if len(title) > self._title_label['max_length']:
            formatted_title = title[:self._title_label['max_length']] + ".."
        else:
            formatted_title = title

        min_length = self._title_label.get('min_length', 0)
        if len(formatted_title) < min_length:
            formatted_title = formatted_title.ljust(min_length)

        return formatted_title

    def _get_app_icon(self, hwnd: int, title:str, process: dict, event: WinEvent, skip_foreground_check=False) -> QPixmap | None:
        try:
            # Skip the foreground check during initial load
            if not skip_foreground_check and hwnd != win32gui.GetForegroundWindow():
                return
            pid = process["pid"]
            cache_key = (hwnd, pid, self.dpi)
            
            if event != WinEvent.WinEventOutOfContext:
                self._update_retry_count = 0

            if cache_key in self._icon_cache:
                icon_img = self._icon_cache[cache_key]
            else:
                self.dpi = self.screen().devicePixelRatio()
                icon_img = get_window_icon(hwnd)
                if icon_img:
                    icon_img = icon_img.resize(
                        (int(self._label_icon_size * self.dpi), int(self._label_icon_size * self.dpi)),
                        Image.LANCZOS
                    ).convert("RGBA")
                else:
                    if process["name"] == "ApplicationFrameHost.exe":
                        if self._update_retry_count < 10:
                            self._update_retry_count += 1
                            QTimer.singleShot(500, lambda: self._get_app_icon(hwnd, title, process, WinEvent.WinEventOutOfContext, skip_foreground_check))
                            return
                        else:
                            self._update_retry_count = 0
                if not DEBUG:
                    self._icon_cache[cache_key] = icon_img
            if not icon_img:
                return None
            qimage = QImage(icon_img.tobytes(), icon_img.width, icon_img.height, QImage.Format.Format_RGBA8888)
            pixmap = QPixmap.fromImage(qimage)
            pixmap.setDevicePixelRatio(self.dpi)
            return pixmap

        except Exception:
            if DEBUG:
                logging.exception(f"Failed to get icons for window with HWND {hwnd} emitted by event {event}")
            return None
            
        
    def get_visible_windows(self, _: int, event: WinEvent) -> list[tuple[str, int, Optional[QPixmap], dict]]:

        visible_windows = []
        def enum_windows_proc(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if not (ex_style & win32con.WS_EX_TOOLWINDOW):
                    title = win32gui.GetWindowText(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    
                    # Skip windows that should be ignored based on title and class
                    if (title in self._ignore_apps['titles'] or 
                        class_name in self._ignore_apps['classes'] or
                        class_name in EXCLUDED_CLASSES):
                        return True
                    
                    # Get the window info to check process name
                    window_info = get_hwnd_info(hwnd)
                    if not window_info or window_info['process']['name'] in self._ignore_apps['processes']:
                        return True

                    process = window_info['process']
                    # First check if we already have this window in our buttons
                    if hwnd in self._window_buttons:
                        # Reuse existing icon if title is the same
                        stored_title, icon, _, _ = self._window_buttons[hwnd]
                        if title == stored_title:
                            visible_windows.append((title, hwnd, icon, process))
                            return True
                    
                    # If not already stored or title changed, get a new icon
                    icon = self._get_app_icon(hwnd, title, process, event)
                    visible_windows.append((title, hwnd, icon, process))

            return True
        
        win32gui.EnumWindows(enum_windows_proc, None)
        return visible_windows
          
    
    def _perform_action(self, action: str) -> None:
        widget = QApplication.instance().widgetAt(QCursor.pos())
        if not widget:
            logging.warning("No widget found under cursor.")
            return
        
        hwnd = widget.property("hwnd")
        if not hwnd:
            logging.warning("No hwnd found for widget.")
            return

        if action == "toggle":
            if self._animation['enabled']:
                AnimationManager.animate(widget, self._animation['type'], self._animation['duration'])
            self.bring_to_foreground(hwnd)
        else:
            logging.warning(f"Unknown action '{action}'.")
         
    
    def _on_toggle_window(self) -> None:
        self._perform_action("toggle")
    
    
    def bring_to_foreground(self, hwnd):
        if not win32gui.IsWindow(hwnd):
            return
        if win32gui.IsIconic(hwnd):
            # If the window is minimized, restore it
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        else:
            # Check if the window is already in the foreground
            foreground_hwnd = win32gui.GetForegroundWindow()
            if hwnd != foreground_hwnd:
                # Bring the window to the foreground
                win32gui.SetForegroundWindow(hwnd)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)


    def _load_initial_windows(self):
        """
        Load all currently visible windows when the widget is first initialized.
        """
        visible_windows = []
        
        def enum_windows_proc(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if not (ex_style & win32con.WS_EX_TOOLWINDOW or ex_style == WS_EX_NOREDIRECTIONBITMAP):
                    title = win32gui.GetWindowText(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    
                    # Skip windows that should be ignored
                    if (title in self._ignore_apps['titles'] or 
                        class_name in self._ignore_apps['classes'] or
                        class_name in EXCLUDED_CLASSES):
                        return True
                    win_info = get_hwnd_info(hwnd)
                    if win_info and win_info['process']['name'] not in self._ignore_apps['processes']:
                        process = win_info['process']
                        icon = self._get_app_icon(hwnd, title, process, WinEvent.WinEventOutOfContext, skip_foreground_check=True)
                        if icon and title:
                            visible_windows.append((title, hwnd, icon, process))
                            
            return True
        
        win32gui.EnumWindows(enum_windows_proc, None)

        if visible_windows:
            for title, hwnd, icon, process in visible_windows:
                if hwnd not in self._window_buttons and icon is not None:
                    self._window_buttons[hwnd] = (title, icon, hwnd, process)
                    
                    icon_label = QLabel()
                    icon_label.setProperty("class", "app-icon")
                    icon_label.setPixmap(icon)
                    if self._tooltip:
                        icon_label.setToolTip(self._format_title(title))
                    icon_label.setProperty("hwnd", hwnd)
                    icon_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    self._widget_container_layout.addWidget(icon_label)
                    # Add title labels during initial load
                    if self._title_label['enabled']:
                        title_label = QLabel(self._format_title(title))
                        title_label.setProperty("class", self._get_title_class(hwnd))
                        title_label.setProperty("hwnd", hwnd)
                        title_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        if self._tooltip:
                            title_label.setToolTip(self._format_title(title))
                        self._widget_container_layout.addWidget(title_label)
                        if self._title_label['show'] == 'focused':
                            title_label.setVisible(self._get_title_visibility(hwnd))

                    
    def _animate_icon(self, icon_label, start_width=None, end_width=None, fps=60, duration=120):
        if start_width is None:
            start_width = 0
        if end_width is None:
            end_width = self._label_icon_size

        step_duration = int(duration / fps)
        width_increment = (end_width - start_width) / fps
        opacity_increment = 1.0 / fps if end_width > start_width else -1.0 / fps

        # Use local variables instead of instance variables
        current_step = 0
        current_width = start_width
        current_opacity = 0.0 if end_width > start_width else 1.0

        # Set up the opacity effect
        opacity_effect = QGraphicsOpacityEffect()
        icon_label.setGraphicsEffect(opacity_effect)
        opacity_effect.setOpacity(current_opacity)

        def update_properties():
            nonlocal current_step, current_width, current_opacity
            if current_step <= fps:
                current_width += width_increment
                current_opacity += opacity_increment
                icon_label.setFixedWidth(int(current_width))
                opacity_effect.setOpacity(current_opacity)
                current_step += 1
            else:
                icon_label._animation_timer.stop()
                if end_width == 0:
                    icon_label.hide()
                    self._widget_container_layout.removeWidget(icon_label)
                    
                    # Also remove the title label if it exists and we're removing an icon
                    hwnd = icon_label.property("hwnd")
                    if self._title_label['enabled'] and hwnd:
                        for i in range(self._widget_container_layout.count()):
                            widget = self._widget_container_layout.itemAt(i).widget()
                            if (widget and widget.property("hwnd") == hwnd and 
                                widget.property("class") and "app-title" in str(widget.property("class"))):
                                self._widget_container_layout.removeWidget(widget)
                                widget.deleteLater()
                                break
                    
                    icon_label.deleteLater()

        # Ensure the label is shown before starting the animation
        icon_label.show()

        # Create a new timer for this animation
        animation_timer = QTimer()
        animation_timer.timeout.connect(update_properties)
        animation_timer.start(step_duration)

        # Store the timer in the icon_label to prevent conflicts
        icon_label._animation_timer = animation_timer
