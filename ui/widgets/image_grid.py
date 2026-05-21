"""VidGen AI - Character image grid widget with alias support."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from config.constants import MAX_CHARACTER_IMAGES


class ImageThumbnail(QWidget):
    """Single image thumbnail with alias input and delete button."""

    remove_clicked = Signal(str)
    alias_changed = Signal(str, str)

    def __init__(self, image_path, alias, parent=None):
        super().__init__(parent)
        self._path = image_path
        self._alias = alias
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        img_label = QLabel()
        img_label.setFixedHeight(64)
        pixmap = QPixmap(self._path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                64,
                64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            img_label.setPixmap(pixmap)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setStyleSheet("background: #171f33; border-radius: 4px; padding: 2px;")
        layout.addWidget(img_label)

        self._alias_input = QLineEdit(self._alias)
        self._alias_input.setPlaceholderText("alias")
        self._alias_input.setFixedHeight(22)
        self._alias_input.setStyleSheet(
            "background: #1e2740; color: #c9d1d9; border: 1px solid #2d3449; "
            "border-radius: 3px; font-size: 10px; padding: 1px 4px;"
        )
        self._alias_input.setToolTip("Tên alias - dùng @alias trong prompt để tham chiếu ảnh này")
        self._alias_input.textChanged.connect(lambda text: self.alias_changed.emit(self._path, text.strip()))
        layout.addWidget(self._alias_input)

        bottom = QHBoxLayout()
        name = QLabel(Path(self._path).name)
        name.setStyleSheet("font-size: 9px; color: #555e7a;")
        bottom.addWidget(name)
        bottom.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(20, 20)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            "background: #dc2626; color: #ffffff; border-radius: 10px; "
            "font-size: 11px; font-weight: bold; border: none;"
        )
        del_btn.clicked.connect(lambda: self.remove_clicked.emit(self._path))
        bottom.addWidget(del_btn)
        layout.addLayout(bottom)

    @property
    def path(self):
        return self._path

    @property
    def alias(self):
        return self._alias_input.text().strip()


class ImageGrid(QWidget):
    """Grid of character reference images with add/remove and per-image alias names."""

    images_changed = Signal(dict)
    changed = images_changed

    def __init__(self, parent=None, show_dispatch_hint: bool = True):
        super().__init__(parent)
        self._images = []
        self._aliases = {}
        self._thumbnails = {}
        self._show_dispatch_hint = show_dispatch_hint
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        title_row = QHBoxLayout()
        title = QLabel("Nhân vật tham chiếu")
        title.setStyleSheet("color: #4EC9B0; font-weight: bold; font-size: 12px;")
        title_row.addWidget(title)
        self.counter = QLabel(f"0/{MAX_CHARACTER_IMAGES}")
        self.counter.setStyleSheet("color: #8c909f; font-size: 11px;")
        title_row.addWidget(self.counter)
        title_row.addStretch()
        main_layout.addLayout(title_row)

        action_row = QHBoxLayout()
        action_row.addStretch()

        clear_btn = QPushButton("Xóa hết")
        clear_btn.setFixedHeight(28)
        clear_btn.setToolTip("Xóa toàn bộ ảnh tham chiếu đã thêm.")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ef4444; border: 1px solid rgba(239,68,68,0.4); "
            "border-radius: 6px; padding: 2px 12px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(239,68,68,0.15); border-color: #ef4444; }"
        )
        clear_btn.clicked.connect(self._on_clear_all)
        self._clear_btn = clear_btn
        action_row.addWidget(clear_btn)

        add_btn = QPushButton("+ Thêm ảnh")
        add_btn.setObjectName("btn-secondary")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet("QPushButton#btn-secondary { padding: 2px 14px; font-size: 11px; }")
        add_btn.setToolTip(
            "Mở hộp thoại chọn ảnh PNG/JPG/WEBP.\n"
            "Mỗi ảnh được gán alias @image1, @image2... tự động.\n"
            "Có thể chọn nhiều ảnh cùng lúc (Ctrl+click)."
        )
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_images)
        self._add_btn = add_btn
        action_row.addWidget(add_btn)
        main_layout.addLayout(action_row)
        self._update_clear_btn()

        if self._show_dispatch_hint:
            help_text = QLabel("💡 Prompt có 1 @image -> video từ ảnh (i2v)  |  2+ @image -> video đồng nhất (r2v)")
            help_text.setWordWrap(True)
            help_text.setStyleSheet(
                "color: #fbbf24; font-size: 11px; font-style: italic; padding: 4px 6px; "
                "background: rgba(251,191,36,0.06); border: 1px dashed rgba(251,191,36,0.3); border-radius: 6px;"
            )
            main_layout.addWidget(help_text)

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(4)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._grid_widget)

    def _next_default_alias(self) -> str:
        existing_aliases = set(self._aliases.values())
        i = 1
        while True:
            candidate = f"image{i}"
            if candidate not in existing_aliases:
                return candidate
            i += 1

    def _add_images(self):
        remaining = MAX_CHARACTER_IMAGES - len(self._images)
        if remaining <= 0:
            return

        try:
            from utils.logger import log

            log.info("[ImageGrid] + Thêm ảnh clicked - opening file dialog")
        except Exception:
            pass

        top = self.window()
        if top:
            top.raise_()
            top.activateWindow()

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn ảnh nhân vật tham chiếu",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*.*)",
        )
        if not paths:
            return

        added = 0
        for path in paths[:remaining]:
            if path in self._images:
                continue
            alias = self._next_default_alias()
            self._images.append(path)
            self._aliases[path] = alias
            added += 1

        if added:
            self._rebuild_grid()
            self.images_changed.emit(self.get_images())
            try:
                from utils.logger import log

                log.info(f"[ImageGrid] Added {added}/{len(paths)} images (total {len(self._images)})")
            except Exception:
                pass

    def add_image(self, path: str):
        if len(self._images) >= MAX_CHARACTER_IMAGES:
            return
        if path not in self._images:
            alias = self._next_default_alias()
            self._images.append(path)
            self._aliases[path] = alias
            self._rebuild_grid()
            self.images_changed.emit(self.get_images())

    def _remove_image(self, path: str):
        if path in self._images:
            self._images.remove(path)
        self._aliases.pop(path, None)
        self._thumbnails.pop(path, None)
        self._rebuild_grid()
        self.images_changed.emit(self.get_images())

    def _on_alias_changed(self, path: str, new_alias: str):
        if path in self._aliases:
            self._aliases[path] = new_alias
        self.images_changed.emit(self.get_images())

    def _rebuild_grid(self):
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._thumbnails.clear()
        cols = 6
        for i, path in enumerate(self._images):
            alias = self._aliases.get(path, f"nv{i + 1}")
            thumb = ImageThumbnail(path, alias=alias)
            thumb.remove_clicked.connect(self._remove_image)
            thumb.alias_changed.connect(self._on_alias_changed)
            self._grid_layout.addWidget(thumb, i // cols, i % cols)
            self._thumbnails[path] = thumb

        self.counter.setText(f"{len(self._images)}/{MAX_CHARACTER_IMAGES}")
        self._update_clear_btn()
        self._grid_layout.invalidate()
        self._grid_widget.adjustSize()
        self._grid_widget.updateGeometry()

    def get_images(self) -> dict[str, str]:
        result = {}
        seen = {}
        for i, path in enumerate(self._images):
            thumb = self._thumbnails.get(path)
            if thumb:
                alias = thumb.alias or self._aliases.get(path, "") or f"ref{i}"
            else:
                alias = self._aliases.get(path, "") or f"ref{i}"

            if alias in result:
                count = seen.get(alias, 1) + 1
                seen[alias] = count
                alias = f"{alias}_{count}"
            else:
                seen[alias] = 1
            result[alias] = path
        return result

    def get_image_paths(self) -> list[str]:
        return list(self._images)

    def clear(self):
        self._images.clear()
        self._aliases.clear()
        self._thumbnails.clear()
        self._rebuild_grid()
        self._update_clear_btn()

    def _on_clear_all(self):
        if not self._images:
            return
        from PySide6.QtWidgets import QMessageBox

        resp = QMessageBox.question(
            self,
            "Xóa tất cả ảnh tham chiếu?",
            f"Sẽ xóa {len(self._images)} ảnh đã thêm. Tiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        self.clear()
        self.images_changed.emit(self.get_images())

    def _update_clear_btn(self):
        if hasattr(self, "_clear_btn"):
            self._clear_btn.setVisible(bool(self._images))
