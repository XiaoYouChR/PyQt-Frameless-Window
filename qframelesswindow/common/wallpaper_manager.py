import sys
import os
import subprocess
import shutil
import configparser
from typing import Optional
from pathlib import Path

if sys.platform == 'win32':
    import winreg

from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import QSize

class WallpaperManager:
    """
    一个跨平台的桌面壁纸管理器.
    所有方法均为静态方法, 无需实例化此类即可调用.
    """

    @staticmethod
    def _createDefaultImage(width: int = 1920, height: int = 1080) -> QImage:
        """创建一个纯色的默认 QImage."""
        image = QImage(QSize(width, height), QImage.Format.Format_RGB32)
        image.fill(QColor(128, 128, 128))  # 填充为中灰色
        return image

    @staticmethod
    def getDesktopWallpaper() -> QImage:
        """
        获取当前桌面壁纸的 QImage 对象.

        此方法保证总是返回一个有效的 QImage. 如果成功获取并加载系统壁纸,
        则返回该壁纸的 QImage; 否则, 返回一个默认的灰色 QImage.

        :return: 代表桌面壁纸或默认图像的 QImage 对象.
        """
        path: Optional[str] = None
        try:
            if sys.platform == "win32":
                path = WallpaperManager._getWindowsWallpaperPath()
            elif sys.platform == "darwin":
                path = WallpaperManager._getMacOSWallpaperPath()
            elif sys.platform == "linux":
                path = WallpaperManager._getLinuxWallpaperPath()
            else:
                print(f"Unsupported platform: {sys.platform}")
        except Exception as e:
            print(f"An unexpected error occurred while getting wallpaper path: {e}")

        if path and os.path.exists(path):
            image = QImage(path)
            if not image.isNull():
                return image
            else:
                print(f"Failed to load image from path: {path}")

        print("Returning default gray image.")
        return WallpaperManager._createDefaultImage()

    # --- 平台特定的路径获取方法 (作为内部实现) ---

    @staticmethod
    def _getWindowsWallpaperPath() -> Optional[str]:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "Wallpaper")
            winreg.CloseKey(key)
            return value
        except Exception as e:
            print(f"Error reading Windows registry: {e}")
            return None

    @staticmethod
    def _getMacOSWallpaperPath() -> Optional[str]:
        if not shutil.which("osascript"):
            print("`osascript` command not found.")
            return None
        try:
            script = 'tell application "Finder" to get posix path of (get desktop picture as alias)'
            process = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=5
            )
            return process.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"AppleScript execution failed or timed out: {e}")
            return None

    @staticmethod
    def _getLinuxWallpaperPath() -> Optional[str]:
        desktopEnv = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()

        path = None
        if 'kde' in desktopEnv or 'plasma' in desktopEnv:
            path = WallpaperManager._getKdeWallpaperPath()

        if not path:
            path = WallpaperManager._getGnomeWallpaperPath()

        if not path:
            print("Could not determine wallpaper for this Linux desktop environment.")

        return path

    @staticmethod
    def _getGnomeWallpaperPath() -> Optional[str]:
        if not shutil.which("gsettings"):
            return None
        schemas = ["picture-uri-dark", "picture-uri"]
        for schema in schemas:
            try:
                command = ["gsettings", "get", "org.gnome.desktop.background", schema]
                process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
                uri = process.stdout.strip().strip("'")
                if uri.startswith("file://"):
                    return uri[7:]
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue
        return None

    @staticmethod
    def _getKdeWallpaperPath() -> Optional[str]:
        try:
            configPath = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"
            if not configPath.is_file(): return None

            config = configparser.ConfigParser()
            config.read(configPath)

            for section in config.sections():
                if section.endswith("General") and 'Image' in config[section]:
                    uri = config[section]['Image']
                    return uri[7:] if uri.startswith("file://") else uri
        except Exception as e:
            print(f"Error parsing KDE config: {e}")
        return None
