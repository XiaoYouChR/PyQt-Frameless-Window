from typing import Callable

from PySide6.QtCore import QObject, QEvent


class UpdateMicaEventFilter(QObject):
    def __init__(self, parent, updateMica: Callable, isDark: bool):
        super().__init__(parent)
        self.parent = parent
        self.updateMica = updateMica
        self.isDark = isDark

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Move or event.type() == QEvent.Type.Resize:
            self.updateMica(obj, self.isDark)
            
        return super().eventFilter(obj, event)
