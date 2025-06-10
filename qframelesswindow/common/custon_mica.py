import sys
import math
from time import perf_counter

from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage, QColor, QPainter
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

        buffer = workImage.bits()

        # 对每一行进行水平模糊
        for row in range(height):
            ExponentialBlur._blurRow(buffer, width, workImage.bytesPerLine(), row, alpha)

        # 对每一列进行垂直模糊
        for col in range(width):
            ExponentialBlur._blurColumn(buffer, width, height, workImage.bytesPerLine(), col, alpha)

        return workImage

    @staticmethod
    def _blurRow(buffer, width, bytesPerLine, row, alpha):
        # 计算当前行的起始字节偏移量
        rowOffset = row * bytesPerLine
        
        # 不用局部变量就慢死人了
        aprec = ExponentialBlur._aprec
        zprec = ExponentialBlur._zprec

        # 从该行的第一个像素初始化 zR, zG, zB, zA 累加器
        # << _zprec 是为了增加计算精度
        accumulators = [
            buffer[rowOffset] << zprec,
            buffer[rowOffset + 1] << zprec,
            buffer[rowOffset + 2] << zprec,
            buffer[rowOffset + 3] << zprec
        ]

        # 正向传递（从左到右）
        for i in range(width):
            offset = rowOffset + i * 4
            ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha, aprec, zprec)

        # 反向传递（从右到左）
        offset = rowOffset + (width - 1) * 4
        # 用行末像素重新初始化累加器以获得正确结果
        accumulators = [
            buffer[offset] << zprec,
            buffer[offset + 1] << zprec,
            buffer[offset + 2] << zprec,
            buffer[offset + 3] << zprec
        ]
        for i in range(width - 2, -1, -1):
            offset = rowOffset + i * 4
            ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha, aprec, zprec)

    @staticmethod
    def _blurColumn(buffer, width, height, bytesPerLine, column, alpha):
        # 计算当前列的第一个像素的偏移量
        colOffset = column * 4
        aprec = ExponentialBlur._aprec
        zprec = ExponentialBlur._zprec

        # 从该列的第一个像素初始化累加器
        accumulators = [
            buffer[colOffset] << zprec,
            buffer[colOffset + 1] << zprec,
            buffer[colOffset + 2] << zprec,
            buffer[colOffset + 3] << zprec
        ]

        # 正向传递（从上到下）
        for i in range(height):
            offset = i * bytesPerLine + colOffset
            ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha, aprec, zprec)

        # 反向传递（从下到上）
        offset = (height - 1) * bytesPerLine + colOffset
        # 用列末像素重新初始化累加器
        accumulators = [
            buffer[offset] << zprec,
            buffer[offset + 1] << zprec,
            buffer[offset + 2] << zprec,
            buffer[offset + 3] << zprec
        ]
        for i in range(height - 2, -1, -1):
            offset = i * bytesPerLine + colOffset
            ExponentialBlur._applyInnerBlur(buffer, offset, accumulators, alpha, aprec, zprec)

    @staticmethod
    def _applyInnerBlur(buffer, offset, accumulators, alpha, aprec, zprec):
        """核心 IIR 滤波器。它会修改缓冲区并返回新的累加器值。"""
        # IIR 滤波公式: z_new = z_old + alpha * (p - z_old)
        # 为了避免浮点运算，使用了定点算术 (<< _zprec, >> _aprec)
        accumulators[0] += (alpha * ((buffer[offset] << zprec) - accumulators[0])) >> aprec
        accumulators[1] += (alpha * ((buffer[offset+1] << zprec) - accumulators[1])) >> aprec
        accumulators[2] += (alpha * ((buffer[offset+2] << zprec) - accumulators[2])) >> aprec
        accumulators[3] += (alpha * ((buffer[offset+3] << zprec) - accumulators[3])) >> aprec

        # 将计算出的新像素值写回缓冲区
        # >> _zprec 用于将值恢复到 0-255 范围
        buffer[offset]     = accumulators[0] >> zprec
        buffer[offset + 1] = accumulators[1] >> zprec
        buffer[offset + 2] = accumulators[2] >> zprec
        buffer[offset + 3] = accumulators[3] >> zprec


class CustomMicaHelper(QObject):
    """
    使用优化的算法生成 Windows 11 Mica 风格的背景图像。
    使用驼峰命名法。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wallpaper = WallpaperManager.getDesktopWallpaper()
        # 在初始化时直接生成两种模式的图像
        self.lightBaseImage, self.darkBaseImage = self.calculateMicaImages()

    def calculateMicaImages(self):
        """
        根据桌面壁纸生成明亮和黑暗主题的 Mica 效果背景。
        此方法通过模糊和颜色叠加来创建更自然、美观的效果。

        :return: (QImage, QImage) 元组，分别为明亮主题和黑暗主题的图像。
        """
        # 1. 为了性能，先将图像缩小再进行模糊处理。
        #    使用稍大的中间尺寸（如 960x540）可以在最终放大时获得更好的质量。
        intermediateSize = QSize(720, 480)
        sourceImage = self.wallpaper.scaled(
            intermediateSize,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # 2. 对缩小后的图像应用强烈的指数模糊。
        #    半径 100-120 在这个尺寸下能产生很好的朦胧效果。
        blurredImage = ExponentialBlur.doExponentialBlur(sourceImage, 150)
        
        blurredImage.save("blurred.png")
        
        # 3. 创建明亮主题的图像
        lightImage = self._createTintedImage(
            blurredImage, QColor(243, 243, 243, 200) # 浅色叠加层，约82%不透明度
        )

        # 4. 创建黑暗主题的图像
        darkImage = self._createTintedImage(
            blurredImage, QColor(32, 32, 32, 200) # 深色叠加层，约86%不透明度
        )

        # 5. 将处理后的图像放大到最终的目标尺寸
        targetSize = QSize(1920, 1080)
        finalLightImage = lightImage.scaled(
            targetSize,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        finalDarkImage = darkImage.scaled(
            targetSize,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        return finalLightImage, finalDarkImage

    def _createTintedImage(self, sourceImage: QImage, tintColor: QColor) -> QImage:
        """
        在源图像上叠加一个半透明的纯色层。

        :param sourceImage: 要处理的基底图像。
        :param tintColor: 带有 alpha 通道的叠加颜色。
        :return: 返回一个新的、已叠加颜色的 QImage。
        """
        # 创建一个副本进行绘制，以免修改原始的 blurredImage
        tintedImage = sourceImage.copy()
        painter = QPainter(tintedImage)

        # 在整个图像区域填充指定的半透明颜色
        painter.fillRect(tintedImage.rect(), tintColor)

        painter.end()
        return tintedImage


if __name__ == "__main__":
    app = QApplication(sys.argv)

    print("正在生成 Mica 效果图像...")
    startTime = perf_counter()

    # 创建 Helper 实例，它会自动生成图像
    helper = CustomMicaHelper()

    # 获取生成的图像
    lightImage = helper.lightBaseImage
    darkImage = helper.darkBaseImage

    executionTime = perf_counter() - startTime
    print(f"执行耗时: {executionTime:.4f} 秒")

    # 保存结果以便查看
    try:
        lightImage.save("mica_light_optimized.png")
        darkImage.save("mica_dark_optimized.png")
        print("优化后的图像已保存为 'mica_light_optimized.png' 和 'mica_dark_optimized.png'")
    except Exception as e:
        print(f"保存图像失败: {e}")

    # 为了在没有GUI循环的情况下使程序退出
    # sys.exit()