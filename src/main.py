import asyncio
import ctypes
import logging
import sys
from sys import argv, exit
import contextlib

import qasync
from PySide6.QtWidgets import QApplication
from dotenv import load_dotenv

import settings
from core.bar_manager import BarManager
from core.config import get_config_and_stylesheet, get_resolved_env_file_path
from core.event_service import EventService
from core.log import init_logger
from core.tray import SystemTrayManager
from core.utils.controller import start_cli_server
from core.watcher import create_observer

logging.getLogger('asyncio').setLevel(logging.WARNING)

@contextlib.contextmanager
def single_instance_lock(name="yasb_reborn"):
    """
    Context manager that creates a Windows mutex to ensure a single instance.
    """
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    if not mutex:
        logging.error("Failed to create mutex.")
        sys.exit(1)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(mutex)
        logging.error("Another instance of the YASB is already running.")
        sys.exit(1)
    try:
        yield mutex
    finally:
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)
   

def main():
    # Initialize configuration early after the single instance check
    config, stylesheet = get_config_and_stylesheet()

    if config['debug']:
        settings.DEBUG = True
        logging.info("Debug mode enabled.")
        
    start_cli_server()
    
    app = QApplication(argv)
    app.setQuitOnLastWindowClosed(False)

    env_file = config.get('env_file')
    if env_file:
        env_file = get_resolved_env_file_path(env_file)
        if load_dotenv(env_file):
            if settings.DEBUG:
                logging.info(f"Loaded environment variables from {env_file}")
        else:
            logging.warning(f"Failed to load environment variables from {env_file}")

    # Need qasync event loop to work with PyQt6
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialise bars and background event listeners
    manager = BarManager(config, stylesheet)
    manager.initialize_bars(init=True)

    # Initialise file watcher if needed
    observer = create_observer(manager) if config['watch_config'] or config['watch_stylesheet'] else None
    if observer:
        observer.start()

    def stop_observer():
        if observer:
            observer.stop()
            observer.join()
    app.aboutToQuit.connect(stop_observer)

    # Build system tray icon
    tray_manager = SystemTrayManager(manager)
    tray_manager.show()
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    init_logger()
    def exception_hook(exctype, value, traceback):
        EventService().clear()
        logging.error("Unhandled exception", exc_info=value)
        sys.exit(1)
    sys.excepthook = exception_hook 

    try:
        # Acquire the single instance lock before doing any heavy initialization
        with single_instance_lock():
            main()
    except Exception as e:
        logging.exception("Exception during application startup")
        sys.exit(1)
