import sys
import math
from time import perf_counter

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from qframelesswindow.common.wallpaper_manager import WallpaperManager


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

        # 获取指向图像内存的可写视图
        # 'bytearray' 比 'memoryview' 略慢，但对于这个算法而言差异可忽略
        buffer = bytearray(workImage.bits())

        # 对每一行进行水平模糊
        for row in range(height):
            ExponentialBlur._blurRow(buffer, width, workImage.bytesPerLine(), row, alpha)

        # 对每一列进行垂直模糊
        for col in range(width):
            ExponentialBlur._blurColumn(buffer, width, height, workImage.bytesPerLine(), col, alpha)

        # 从修改后的缓冲区创建一个新的 QImage
        return QImage(buffer, width, height, workImage.bytesPerLine(), QImage.Format.Format_ARGB32_Premultiplied)

    @staticmethod
    def _blurRow(buffer, width, bytesPerLine, row, alpha):
        # 计算当前行的起始字节偏移量
        rowOffset = row * bytesPerLine

        # 从该行的第一个像素初始化 zR, zG, zB, zA 累加器
        # << _zprec 是为了增加计算精度
        accumulators = [
            buffer[rowOffset] << ExponentialBlur._zprec,
            buffer[rowOffset + 1] << ExponentialBlur._zprec,
            buffer[rowOffset + 2] << ExponentialBlur._zprec,
            buffer[rowOffset + 3] << ExponentialBlur._zprec
        ]

        # 正向传递（从左到右）
        for i in range(width):
            offset = rowOffset + i * 4
            accumulators = ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha)

        # 反向传递（从右到左）
        # 从倒数第二个像素开始
        offset = rowOffset + (width - 1) * 4
        # 用行末像素重新初始化累加器
        accumulators = [
            buffer[offset] << ExponentialBlur._zprec,
            buffer[offset + 1] << ExponentialBlur._zprec,
            buffer[offset + 2] << ExponentialBlur._zprec,
            buffer[offset + 3] << ExponentialBlur._zprec
        ]
        for i in range(width - 2, -1, -1):
            offset = rowOffset + i * 4
            accumulators = ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha)


    @staticmethod
    def _blurColumn(buffer, width, height, bytesPerLine, column, alpha):
        # 计算当前列的第一个像素的偏移量
        colOffset = column * 4

        # 从该列的第一个像素初始化累加器
        accumulators = [
            buffer[colOffset] << ExponentialBlur._zprec,
            buffer[colOffset + 1] << ExponentialBlur._zprec,
            buffer[colOffset + 2] << ExponentialBlur._zprec,
            buffer[colOffset + 3] << ExponentialBlur._zprec
        ]

        # 正向传递（从上到下）
        for i in range(height):
            offset = i * bytesPerLine + colOffset
            accumulators = ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha)

        # 反向传递（从下到上）
        # 从列末像素重新初始化累加器
        offset = (height - 1) * bytesPerLine + colOffset
        accumulators = [
            buffer[offset] << ExponentialBlur._zprec,
            buffer[offset + 1] << ExponentialBlur._zprec,
            buffer[offset + 2] << ExponentialBlur._zprec,
            buffer[offset + 3] << ExponentialBlur._zprec
        ]
        for i in range(height - 2, -1, -1):
            offset = i * bytesPerLine + colOffset
            accumulators = ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha)

    @staticmethod
    def _applyInnerBlur(buffer, offset, accumulators, alpha):
        """核心 IIR 滤波器。它会修改缓冲区并返回新的累加器值。"""
        # 读取当前像素的 BGRA 值 (QImage 内存布局通常是 BGRA)
        pixelValues = [buffer[offset], buffer[offset+1], buffer[offset+2], buffer[offset+3]]

        # IIR 滤波公式: z_new = z_old + alpha * (p - z_old)
        # 为了避免浮点运算，使用了定点算术 (<< _zprec, >> _aprec)
        accumulators[0] += (alpha * ((pixelValues[0] << ExponentialBlur._zprec) - accumulators[0])) >> ExponentialBlur._aprec
        accumulators[1] += (alpha * ((pixelValues[1] << ExponentialBlur._zprec) - accumulators[1])) >> ExponentialBlur._aprec
        accumulators[2] += (alpha * ((pixelValues[2] << ExponentialBlur._zprec) - accumulators[2])) >> ExponentialBlur._aprec
        accumulators[3] += (alpha * ((pixelValues[3] << ExponentialBlur._zprec) - accumulators[3])) >> ExponentialBlur._aprec

        # 将计算出的新像素值写回缓冲区
        # >> _zprec 用于将值恢复到 0-255 范围
        buffer[offset]     = accumulators[0] >> ExponentialBlur._zprec
        buffer[offset + 1] = accumulators[1] >> ExponentialBlur._zprec
        buffer[offset + 2] = accumulators[2] >> ExponentialBlur._zprec
        buffer[offset + 3] = accumulators[3] >> ExponentialBlur._zprec

        # 返回更新后的累加器值
        return accumulators


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
        img = img.scaled(QSize(640, 360), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # 调用我们实现的指数模糊函数。
        # 注意：C++ 版本返回 QPixmap 后调用了 .toImage()。
        # 我们的 Python 版本直接返回 QImage，因此无需转换。
        blurImage = ExponentialBlur.doExponentialBlur(img, 500)

        # 使用 .copy() 来创建独立的图像副本，而不是引用
        lightImage = blurImage.copy()
        darkImage = blurImage.copy()


        blurBits = blurImage.constBits()
        lightBits = lightImage.bits()
        darkBits = darkImage.bits()

        bytesPerPixel = 4 # ARGB32_Premultiplied 格式每个像素占4字节

        # 使用单个循环遍历整个图像缓冲区
        for i in range(0, blurImage.sizeInBytes(), bytesPerPixel):
            # 从缓冲区读取 BGRA 值
            # 注意: QImage 在内存中通常是 BGRA 顺序
            b, g, r = blurBits[i], blurBits[i+1], blurBits[i+2]

            # QColor.fromRgb 需要 (R, G, B) 顺序
            # .getHsv() 返回 (h, s, v, a) 元组。h 为 -1 表示灰度色
            h, s, v, _ = QColor(r, g, b).getHsv()

            # --- 计算明亮主题颜色 ---
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

            # 将计算出的颜色值直接写回 lightImage 的内存缓冲区
            lightBits[i] = lightColor.blue()
            lightBits[i+1] = lightColor.green()
            lightBits[i+2] = lightColor.red()
            # Alpha 通道保持不变

            # 将计算出的颜色值直接写回 darkImage 的内存缓冲区
            darkBits[i] = darkColor.blue()
            darkBits[i+1] = darkColor.green()
            darkBits[i+2] = darkColor.red()
            # Alpha 通道保持不变

        self._lightBaseImage = lightImage.scaled(QSize(1920, 1080), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._darkBaseImage = darkImage.scaled(QSize(1920, 1080), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

        # 调试
        self._lightBaseImage.save("light.png", "PNG")
        self._darkBaseImage.save("dark.png", "PNG")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    time = perf_counter()
    helper = CustomMicaHelper()
    print(f"执行耗时: {perf_counter() - time:.4f} 秒")