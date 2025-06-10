import sys
from time import perf_counter

import numpy as np
from scipy.ndimage.filters import gaussian_filter
from PIL import Image
from PySide6.QtCore import QObject, QSize, Qt
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication

from qframelesswindow.common.wallpaper_manager import WallpaperManager

class CustomMicaHelper(QObject):
    """
    使用优化的算法生成 Windows 11 Mica 风格的背景图像。
    使用驼峰命名法。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.wallpaper = WallpaperManager.getDesktopWallpaper()
        self.lightMicaImage, self.darkMicaImage = self.generateMicaImages()

    def gaussianBlur(self, blurRadius=18, brightFactor=1, blurPicSize=None):
        image = Image.fromqimage(self.wallpaper)

        if blurPicSize:
            # adjust image size to reduce computation
            w, h = image.size
            ratio = min(blurPicSize[0] / w, blurPicSize[1] / h)
            w_, h_ = w * ratio, h * ratio
    
            if w_ < w:
                image = image.resize((int(w_), int(h_)), Image.LANCZOS)
    
        image = np.array(image)
    
        # handle gray image
        if len(image.shape) == 2:
            image = np.stack([image, image, image], axis=-1)
    
        # blur each channel
        for i in range(3):
            image[:, :, i] = gaussian_filter(
                image[:, :, i], blurRadius) * brightFactor
    
        # convert ndarray to QPixmap
        h, w, c = image.shape
        if c == 3:
            format = QImage.Format.Format_RGB888
        else:
            format = QImage.Format.Format_RGBA8888
    
        return QImage(image.data, w, h, c*w, format)
    
    def generateMicaImages(self):
        """
        根据桌面壁纸生成明亮和黑暗主题的 Mica 效果背景。
        此方法通过模糊、颜色叠加和噪点来创建更自然、美观的效果。

        :return: (QImage, QImage) 元组，分别为明亮主题和黑暗主题的图像。
        """
        self.blurredWallpaper = self.gaussianBlur(blurRadius=120, blurPicSize=(960, 540))

        lightImage = self._createMicaEffect(self.blurredWallpaper, isDark=False)
        darkImage = self._createMicaEffect(self.blurredWallpaper, isDark=True)

        targetSize = QSize(1920, 1080)
        lightImage = lightImage.scaled(
            targetSize,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        darkImage = darkImage.scaled(
            targetSize,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        return lightImage, darkImage

    def _createMicaEffect(self, sourceImage: QImage, isDark: bool) -> QImage:
        """
        在模糊的源图像上应用优化的Mica效果。

        :param sourceImage: 经过高斯模糊处理的基底图像。
        :param isDark: True表示生成暗黑主题，False表示生成明亮主题。
        :return: 返回一个新的、带有Mica效果的QImage。
        """
        # 定义一个非常微妙的白色高光层，增加层次感
        tintColor = QColor(255, 255, 255, 10)

        if isDark:
            luminosityColor = QColor(42, 42, 42, 220)
            noiseOpacity = 0.035
        else:
            luminosityColor = QColor(243, 243, 243, 220)
            noiseOpacity = 0.02

        resultImage = QImage(sourceImage.size(), QImage.Format.Format_ARGB32_Premultiplied)

        painter = QPainter(resultImage)

        # 填充基色层
        painter.fillRect(resultImage.rect(), luminosityColor)

        # 使用Overlay模式混合模糊壁纸，保留颜色并调整明暗
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
        painter.drawImage(0, 0, sourceImage)

        # 恢复默认模式，叠加微妙的白色高光
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.fillRect(resultImage.rect(), tintColor)

        # 叠加噪点以增强质感
        noiseImage = self._createNoiseImage(sourceImage.width(), sourceImage.height(), isDark)
        painter.setOpacity(noiseOpacity)
        painter.drawImage(0, 0, noiseImage)
        painter.setOpacity(1.0) # 恢复不透明度

        painter.end()

        return resultImage

    def _createNoiseImage(self, width: int, height: int, isDark: bool) -> QImage:
        """
        生成一张灰度噪点图像。
        """
        # 使用 numpy 生成随机噪点
        if isDark:
            # 暗模式下噪点可以更亮一些以形成对比
            intensity = np.random.randint(0, 100, size=(height, width), dtype=np.uint8)
        else:
            # 亮模式下噪点偏暗
            intensity = np.random.randint(150, 255, size=(height, width), dtype=np.uint8)

        # 将灰度数组扩展为 BGRA (QImage.Format_ARGB32 需要)
        # Qt 在小端系统上内存布局是 BGRA
        image_array = np.stack([intensity, intensity, intensity, np.full((height,width), 255, dtype=np.uint8)], axis=-1)

        noise = QImage(image_array.data, width, height, QImage.Format.Format_ARGB32).copy()
        return noise


if __name__ == "__main__":
    app = QApplication(sys.argv)

    print("正在生成 Mica 效果图像...")
    startTime = perf_counter()

    # 创建 Helper 实例，它会自动生成图像
    helper = CustomMicaHelper()

    executionTime = perf_counter() - startTime
    print(f"执行耗时: {executionTime:.4f} 秒")
    
    helper.blurredWallpaper.save("blurred_wallpaper.png")
    helper.lightMicaImage.save("mica_light_optimized.png")
    helper.darkMicaImage.save("mica_dark_optimized.png")