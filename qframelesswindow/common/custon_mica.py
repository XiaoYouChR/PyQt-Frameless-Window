import sys
from time import perf_counter

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget, QApplication
from pywin.scintilla.configui import paletteVGA

from qframelesswindow.common.wallpaper_manager import WallpaperManager


import math
from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QColor

class ExponentialBlur:
    """
    一个基于 IIR 的指数模糊算法的 Python 实现
    """
    # 算法的精度常量
    _aprec = 12
    _zprec = 7

    @staticmethod
    def doExponentialBlur(img: QImage, blurRadius: int) -> QImage:
        """
        对 QImage 执行指数模糊。

        :param img: 要模糊的输入 QImage。
        :param blurRadius: 模糊半径，值越大越模糊。
        :return: 返回一个新的、已模糊的 QImage。
        """
        if blurRadius < 1:
            return img.copy()

        # 为了进行像素操作，转换为预乘 ARGB 格式
        # 使用 copy() 确保我们不会修改原始传入的图像
        workImage = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

        # 根据模糊半径计算 alpha 值，这是 IIR 滤波器的关键参数
        alpha = int((1 << ExponentialBlur._aprec) * (1.0 - math.exp(-2.3 / (blurRadius + 1.0))))

        height = workImage.height()
        width = workImage.width()

        buffer = bytearray(workImage.bits())

        # 对每一行进行水平模糊
        for row in range(height):
            ExponentialBlur._drawRowBlur(buffer, width, workImage.bytesPerLine(), row, alpha)

        # 对每一列进行垂直模糊
        for col in range(width):
            ExponentialBlur._drawColumnBlur(buffer, width, height, workImage.bytesPerLine(), col, alpha)

        return QImage(buffer, width, height, workImage.bytesPerLine(), QImage.Format.Format_ARGB32_Premultiplied)

    @staticmethod
    def _drawRowBlur(buffer, width, bytesPerLine, row, alpha):
        # 计算当前行的起始字节偏移量
        row_offset = row * bytesPerLine

        # 从该行的第一个像素初始化 zR, zG, zB, zA 累加器
        # << _zprec 是为了增加计算精度
        z = [
            buffer[row_offset] << ExponentialBlur._zprec,
            buffer[row_offset + 1] << ExponentialBlur._zprec,
            buffer[row_offset + 2] << ExponentialBlur._zprec,
            buffer[row_offset + 3] << ExponentialBlur._zprec
        ]

        # 正向传递（从左到右）
        for i in range(width):
            offset = row_offset + i * 4
            z = ExponentialBlur._drawInnerBlur(buffer, offset, z, alpha)

        # 反向传递（从右到左）
        for i in range(width - 2, -1, -1):
            offset = row_offset + i * 4
            z = ExponentialBlur._drawInnerBlur(buffer, offset, z, alpha)

    @staticmethod
    def _drawColumnBlur(buffer, width, height, bytesPerLine, column, alpha):
        # 计算当前列的第一个像素的偏移量
        col_offset = column * 4

        # 从该列的第一个像素初始化累加器
        z = [
            buffer[col_offset] << ExponentialBlur._zprec,
            buffer[col_offset + 1] << ExponentialBlur._zprec,
            buffer[col_offset + 2] << ExponentialBlur._zprec,
            buffer[col_offset + 3] << ExponentialBlur._zprec
        ]

        # 正向传递（从上到下）
        # 跳过第一个像素，因为它已用于初始化
        for i in range(1, height):
            offset = i * bytesPerLine + col_offset
            z = ExponentialBlur._drawInnerBlur(buffer, offset, z, alpha)

        # 反向传递（从下到上）
        for i in range(height - 2, -1, -1):
            offset = i * bytesPerLine + col_offset
            z = ExponentialBlur._drawInnerBlur(buffer, offset, z, alpha)

    @staticmethod
    def _drawInnerBlur(bptr, offset, z_vals, alpha):
        """核心 IIR 滤波器。它会修改缓冲区并返回新的累加器值。"""
        # 读取当前像素的 BGRA 值
        pixel_vals = [bptr[offset], bptr[offset+1], bptr[offset+2], bptr[offset+3]]

        # C++ 中 zR, zG, zB, zA 是通过引用传递的，这里我们直接修改列表元素
        # IIR 滤波公式: z_new = z_old + alpha * (p - z_old)
        # 为了避免浮点运算，使用了定点算术 (<< _zprec, >> _aprec)
        z_vals[0] += (alpha * ((pixel_vals[0] << ExponentialBlur._zprec) - z_vals[0])) >> ExponentialBlur._aprec
        z_vals[1] += (alpha * ((pixel_vals[1] << ExponentialBlur._zprec) - z_vals[1])) >> ExponentialBlur._aprec
        z_vals[2] += (alpha * ((pixel_vals[2] << ExponentialBlur._zprec) - z_vals[2])) >> ExponentialBlur._aprec
        z_vals[3] += (alpha * ((pixel_vals[3] << ExponentialBlur._zprec) - z_vals[3])) >> ExponentialBlur._aprec

        # 将计算出的新像素值写回缓冲区
        # >> _zprec 用于将值恢复到 0-255 范围
        bptr[offset]     = z_vals[0] >> ExponentialBlur._zprec
        bptr[offset + 1] = z_vals[1] >> ExponentialBlur._zprec
        bptr[offset + 2] = z_vals[2] >> ExponentialBlur._zprec
        bptr[offset + 3] = z_vals[3] >> ExponentialBlur._zprec

        # 返回更新后的累加器值
        return z_vals


class CustomMicaHelper(QObject):
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wallpaper: QImage = WallpaperManager.getDesktopWallpaper()
        self.onInitMicaBase(self.wallpaper)

    def onInitMicaBase(self, img: QImage):
        """
        根据输入图像生成明亮和黑暗主题的云母效果背景。

        :param img: QImage, 输入的原始图像。
        """
        # 统一处理为 1920*1080 以节省空间
        img = img.scaled(QSize(1920, 1080), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # 调用我们实现的指数模糊函数。
        # 注意：C++ 版本返回 QPixmap 后调用了 .toImage()。
        # 我们的 Python 版本直接返回 QImage，因此无需转换。
        blurImage = ExponentialBlur.doExponentialBlur(img, 500)

        # 使用 .copy() 来创建独立的图像副本，而不是引用
        lightImage = blurImage.copy()
        darkImage = blurImage.copy()

        # 遍历图像的每一个像素以生成亮/暗主题版本
        for y in range(blurImage.height()):
            for x in range(blurImage.width()):
                originColor = blurImage.pixelColor(x, y)
                originColorHsv = originColor.toHsv()

                h = originColorHsv.hsvHue()
                s = originColorHsv.hsvSaturation()
                v = originColorHsv.value()

                # --- 计算明亮主题颜色 ---
                # C++ 中整数间的 `/` 是整数除法，Python 中使用 `//` 匹配
                if s // 20 > 11:
                    newLightSaturation = (s // 20 + 11) // 2
                    lightColor = QColor.fromHsv(h, newLightSaturation, 250)
                else:
                    lightColor = QColor.fromHsv(h, 11, 250)

                # --- 计算黑暗主题颜色 ---
                if v / 1.1 > 40:
                    newDarkValue = int((v / 1.1 + 40) / 2)
                    darkColor = QColor.fromHsv(h, s // 2, newDarkValue)
                else:
                    darkColor = QColor.fromHsv(h, s // 2, 40)

                # PySide 的 setPixelColor 直接接受 QColor 对象，更方便
                lightImage.setPixelColor(x, y, lightColor)
                darkImage.setPixelColor(x, y, darkColor)

        # 将处理后的图像存储到成员变量中
        self._lightBaseImage = lightImage.copy()
        self._darkBaseImage = darkImage.copy()

        # 可以取消注释以保存图像进行调试
        self._lightBaseImage.save("light.png", "PNG")
        self._darkBaseImage.save("dark.png", "PNG")
    
    # def _updateMica(self, window: QWidget, isDark: bool = False):
    #     palette = window.palette()
    #     
    #     if isDark:
    # 

if __name__ == "__main__":
    time = perf_counter()
    helper = CustomMicaHelper()
    print(perf_counter() - time)