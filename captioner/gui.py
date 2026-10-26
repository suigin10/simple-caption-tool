from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCloseEvent, QFont, QFontDatabase, QIcon, QImageReader, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .core import Project, Settings, now, render, resolve_trigger
from .runtime import CATALOG
from .preferences import Preferences
from .worker import AnalysisWorker

STATUS = {"pending": "未解析", "running": "解析中", "done": "解析済み", "error": "エラー", "missing": "画像なし"}


def configure_app(app: QApplication):
    app.setStyle("Fusion")
    # Explicit font loading also supports headless QA where platform font discovery is absent.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "meiryo.ttc"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 9))
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: "#edf2f7", QPalette.ColorRole.WindowText: "#172b45",
        QPalette.ColorRole.Base: "#ffffff", QPalette.ColorRole.AlternateBase: "#f2f6fb",
        QPalette.ColorRole.Text: "#172b45", QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#172b45", QPalette.ColorRole.Highlight: "#1d4ed8",
        QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.PlaceholderText: "#64748b",
        QPalette.ColorRole.ToolTipBase: "#ffffff", QPalette.ColorRole.ToolTipText: "#172b45",
    }.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6b7c90"))
    app.setPalette(palette)
    check_icon = (Path(__file__).parent / "icons" / "check.svg").as_posix()
    down_icon = (Path(__file__).parent / "icons" / "down.svg").as_posix()
    up_icon = (Path(__file__).parent / "icons" / "up.svg").as_posix()
    app.setStyleSheet("""
        QMainWindow { background: #edf2f7; }
        QLabel, QCheckBox { color: #172b45; }
        QLabel#triggerPreview { color: #17459e; padding: 3px 0; }
        QPushButton { background: #ffffff; color: #172b45; border: 1px solid #8d9fb5;
                      border-radius: 5px; padding: 6px 10px; }
        QPushButton:hover { background: #e8f0ff; border-color: #2563eb; }
        QPushButton:pressed { background: #d4e3ff; }
        QPushButton:disabled { background: #e2e8f0; color: #6b7c90; border-color: #c2cdda; }
        QPushButton#primaryAction { background: #1d4ed8; color: white; border-color: #1d4ed8; }
        QPushButton#primaryAction:hover { background: #1740af; }
        QPushButton#primaryAction:disabled { background: #d8e2ef; color: #6b7c90; border-color: #c2cdda; }
        QPlainTextEdit, QListWidget { background: white; color: #172b45; border: 1px solid #9cacc0;
                                     border-radius: 5px; selection-background-color: #1d4ed8;
                                     selection-color: white; }
        QListWidget::item:selected { background: #1d4ed8; color: white; }
        QLineEdit, QComboBox, QSpinBox { background: white; color: #172b45; border: 1px solid #8d9fb5;
                                       border-radius: 4px; padding: 4px; }
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #2563eb; }
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { background: #e2e8f0; color: #6b7c90; }
        QComboBox QAbstractItemView { background: white; color: #172b45;
                                    selection-background-color: #1d4ed8; selection-color: white; }
        QComboBox { padding-right: 26px; }
        QComboBox::drop-down { width: 22px; border: none; border-left: 1px solid #b3c1d2; background: #e8eef7; }
        QComboBox::down-arrow { image: url("DOWN_ICON"); width: 12px; height: 12px; }
        QSpinBox { padding-right: 24px; }
        QSpinBox::up-button, QSpinBox::down-button { width: 20px; background: #e8eef7; border-left: 1px solid #b3c1d2; }
        QSpinBox::up-arrow { image: url("UP_ICON"); width: 10px; height: 10px; }
        QSpinBox::down-arrow { image: url("DOWN_ICON"); width: 10px; height: 10px; }
        QCheckBox { spacing: 9px; padding: 3px 2px; }
        QCheckBox:disabled, QLabel:disabled { color: #6b7c90; }
        QCheckBox::indicator { width: 20px; height: 20px; border-radius: 4px; }
        QCheckBox::indicator:unchecked { background: white; border: 2px solid #64748b; }
        QCheckBox::indicator:unchecked:hover { border-color: #2563eb; background: #e8f0ff; }
        QCheckBox::indicator:checked { background: #1d4ed8; border: 2px solid #1d4ed8;
                                      image: url("CHECK_ICON"); }
        QCheckBox::indicator:checked:hover { background: #1740af; }
        QCheckBox::indicator:unchecked:disabled { background: #e2e8f0; border-color: #a7b5c6; }
        QCheckBox::indicator:checked:disabled { background: #8295b0; border-color: #8295b0; }
        QTabWidget::pane { border: 1px solid #9cacc0; background: white; }
        QTabBar::tab { background: #dce5f0; color: #334b68; padding: 6px 12px; }
        QTabBar::tab:selected { background: white; color: #17459e; }
        QStatusBar { background: #e0e8f2; color: #334b68; }
    """.replace("CHECK_ICON", check_icon).replace("DOWN_ICON", down_icon).replace("UP_ICON", up_icon))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("simple caption tool")
        self.resize(1280, 940)
        self.preferences = Preferences()
        self.project: Project | None = None
        self.project_lock: QLockFile | None = None
        self.worker: AnalysisWorker | None = None
        self.current_key: str | None = None
        self.loading = False
        self.write_failed = False
        self.items: dict[str, QListWidgetItem] = {}
        self.thumbnails: list[str] = []
        self.close_requested = False
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.safe_save)
        self.thumb_timer = QTimer(self)
        self.thumb_timer.timeout.connect(self.load_thumbnails)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.open_button = QPushButton("画像フォルダーを開く")
        self.open_button.clicked.connect(self.open_folder)
        toolbar.addWidget(self.open_button)
        self.folder_label = QLabel("画像はこのPC内だけで処理されます")
        self.folder_label.setWordWrap(True)
        toolbar.addWidget(self.folder_label, 1)
        layout.addLayout(toolbar)
        self.settings_box = QWidget()
        form = QFormLayout(self.settings_box)
        row = QHBoxLayout()
        self.target = QComboBox()
        self.target.addItem("キャラクターLoRA", "character")
        self.target.addItem("画風LoRA", "style")
        self.output_format = QComboBox()
        for label, value in [("自然文", "natural"), ("タグ", "tags"), ("自然文＋タグ", "mixed")]:
            self.output_format.addItem(label, value)
        self.trigger = QLineEdit()
        self.trigger.setPlaceholderText("例: my_character / my_style")
        row.addWidget(self.target)
        row.addWidget(self.output_format)
        row.addWidget(QLabel("トリガー"))
        row.addWidget(self.trigger, 1)
        form.addRow("学習・出力", row)
        trigger_row = QHBoxLayout()
        self.trigger_source = QComboBox()
        self.trigger_source.addItem("共通トリガーを入力", "manual")
        self.trigger_source.addItem("ファイル名の先頭を使う", "filename")
        self.trigger_length = QSpinBox()
        self.trigger_length.setRange(1, 999)
        self.trigger_unit = QComboBox()
        self.trigger_unit.addItem("単語", "words")
        self.trigger_unit.addItem("文字", "characters")
        self.trigger_separators = QLineEdit("_-")
        self.trigger_separators.setMaximumWidth(110)
        self.trigger_separators.setToolTip("単語の区切りに使う文字。空白も常に区切りとして扱います。区切り自体は名前の中に残します。")
        trigger_row.addWidget(self.trigger_source)
        trigger_row.addWidget(QLabel("先頭から"))
        trigger_row.addWidget(self.trigger_length)
        trigger_row.addWidget(self.trigger_unit)
        trigger_row.addWidget(QLabel("単語の区切り"))
        trigger_row.addWidget(self.trigger_separators)
        trigger_row.addStretch(1)
        form.addRow("トリガーの指定", trigger_row)
        self.trigger_preview = QLabel()
        self.trigger_preview.setObjectName("triggerPreview")
        self.trigger_preview.setWordWrap(True)
        form.addRow("適用例", self.trigger_preview)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        for key, model in CATALOG["models"].items():
            self.model.addItem(model["label"], key)
        model_row.addWidget(self.model, 1)
        self.layers = QSpinBox()
        self.layers.setRange(0, 99)
        self.layers.setValue(99)
        self.layers.setToolTip("メモリ不足時は減らしてください。0でCPU実行")
        model_row.addWidget(QLabel("GPU層数"))
        model_row.addWidget(self.layers)
        self.edge = QComboBox()
        for size in (768, 1024, 1536):
            self.edge.addItem(str(size), size)
        self.edge.setCurrentIndex(1)
        model_row.addWidget(QLabel("解析画像の最大辺"))
        model_row.addWidget(self.edge)
        form.addRow("解析モデル", model_row)
        self.appearance_hint = QLabel("目の色・髪色・髪型・服装を、タグ・自然文の両方で記述します。")
        self.appearance_hint.setWordWrap(True)
        form.addRow("記述内容", self.appearance_hint)
        self.mode_hint = QLabel()
        self.mode_hint.setWordWrap(True)
        form.addRow("", self.mode_hint)
        layout.addWidget(self.settings_box)
        actions = QHBoxLayout()
        self.pending_button = QPushButton("未解析・失敗を解析／再開")
        self.pending_button.setObjectName("primaryAction")
        self.pending_button.clicked.connect(lambda: self.start_analysis(False))
        self.force_button = QPushButton("選択画像を再解析")
        self.force_button.clicked.connect(lambda: self.start_analysis(True))
        self.all_button = QPushButton("すべての画像を再解析")
        self.all_button.setToolTip("選択や表示フィルターにかかわらず、解析済みも含む全画像を解析し直します。手動編集は上書きチェックに従います。")
        self.all_button.clicked.connect(lambda: self.start_analysis(True, all_records=True))
        self.cancel_button = QPushButton("中止（現在の1枚の完了後）")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        for button in (self.pending_button, self.force_button, self.all_button, self.cancel_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        splitter = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.filter = QComboBox()
        for label, key in [("すべて", "all"), ("未解析", "pending"), ("解析済み", "done"),
                           ("エラー", "error"), ("手動編集済み", "edited")]:
            self.filter.addItem(label, key)
        self.filter.currentIndexChanged.connect(self.refresh_filter)
        left_layout.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(88, 88))
        self.list.currentItemChanged.connect(self.select_image)
        left_layout.addWidget(self.list)
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.image_label = QLabel("フォルダーを開いて画像を選択してください")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(180)
        self.image_label.setMaximumHeight(270)
        right_layout.addWidget(self.image_label)
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        right_layout.addWidget(self.file_label)
        tabs = QTabWidget()
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("キャプションを編集できます。編集内容はJSONへ自動保存されます。")
        self.editor.textChanged.connect(self.editor_changed)
        tabs.addTab(self.editor, "出力キャプション（編集可）")
        self.analysis_view = QPlainTextEdit()
        self.analysis_view.setReadOnly(True)
        tabs.addTab(self.analysis_view, "解析JSON・履歴")
        right_layout.addWidget(tabs, 1)
        splitter.addWidget(right)
        splitter.setSizes([390, 800])
        layout.addWidget(splitter, 1)
        self.edit_box = QWidget()
        edits = QVBoxLayout(self.edit_box)
        edits.setContentsMargins(0, 0, 0, 0)
        render_row = QHBoxLayout()
        self.allow_edited = QCheckBox("手動編集済みも再生成・再解析で上書きする")
        render_row.addWidget(self.allow_edited, 1)
        rebuild = QPushButton("JSONから選択を再生成")
        rebuild.clicked.connect(lambda: self.rebuild(False))
        rebuild_all = QPushButton("JSONから全件を再生成")
        rebuild_all.clicked.connect(lambda: self.rebuild(True))
        render_row.addWidget(rebuild)
        render_row.addWidget(rebuild_all)
        edits.addLayout(render_row)
        replace_row = QHBoxLayout()
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("検索する文字列（完全一致）")
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("置換後の文字列")
        replace_row.addWidget(self.find_text)
        replace_row.addWidget(self.replace_text)
        replace_selected = QPushButton("選択を置換")
        replace_selected.clicked.connect(lambda: self.replace(False))
        replace_all = QPushButton("全件を置換")
        replace_all.clicked.connect(lambda: self.replace(True))
        replace_row.addWidget(replace_selected)
        replace_row.addWidget(replace_all)
        edits.addLayout(replace_row)
        export_row = QHBoxLayout()
        self.overwrite_txt = QCheckBox("既存TXTをバックアップして上書きする")
        export_row.addWidget(self.overwrite_txt, 1)
        export_button = QPushButton("画像と同名のUTF-8 TXTを一括出力")
        export_button.setObjectName("primaryAction")
        export_button.clicked.connect(self.export)
        export_row.addWidget(export_button)
        edits.addLayout(export_row)
        layout.addWidget(self.edit_box)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        for control in (self.target, self.output_format, self.model, self.edge, self.trigger_source, self.trigger_unit):
            control.currentIndexChanged.connect(self.settings_changed)
        self.layers.valueChanged.connect(self.settings_changed)
        self.trigger.textChanged.connect(self.settings_changed)
        self.trigger_length.valueChanged.connect(self.settings_changed)
        self.trigger_separators.textChanged.connect(self.settings_changed)
        self.allow_edited.toggled.connect(self.settings_changed)
        self.overwrite_txt.toggled.connect(self.settings_changed)
        self.filter.currentIndexChanged.connect(self.settings_changed)
        self.apply_settings(self.preferences.settings)
        self.loading = True
        self.allow_edited.setChecked(self.preferences.allow_edited)
        self.overwrite_txt.setChecked(self.preferences.overwrite_txt)
        self.filter.setCurrentIndex(max(0, self.filter.findData(self.preferences.filter)))
        self.loading = False
        self.settings_changed()
        self.statusBar().showMessage("初回の解析時のみモデルと推論エンジンを取得します。画像の外部送信はありません。")
        if self.preferences.load_error:
            self.statusBar().showMessage("前回のアプリ設定を読み込めなかったため、初期設定を表示しています。")

    def safe_save(self) -> bool:
        try:
            self.preferences.settings = self.read_settings()
            self.preferences.allow_edited = self.allow_edited.isChecked()
            self.preferences.overwrite_txt = self.overwrite_txt.isChecked()
            self.preferences.filter = self.filter.currentData()
            if self.project is not None:
                self.preferences.last_folder = str(self.project.root)
                self.project.save()
            self.preferences.save()
            self.write_failed = False
            return True
        except OSError as error:
            self.write_failed = True
            if self.worker:
                self.worker.cancel.set()
            QMessageBox.critical(self, "保存できません", str(error) + "\nフォルダーの権限・空き容量を確認してください。")
            return False

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "画像フォルダーを選択", self.preferences.last_folder)
        if folder:
            self.load_project(Path(folder))

    def load_project(self, root: Path):
        if self.project is not None and not self.safe_save():
            return
        root = root.resolve()
        same_project = self.project is not None and self.project.root == root
        new_lock = self.project_lock if same_project else None
        try:
            if not same_project:
                lock_folder = root / ".captioner"
                lock_folder.mkdir(parents=True, exist_ok=True)
                new_lock = QLockFile(str(lock_folder / "project.lock"))
                if not new_lock.tryLock(0):
                    raise RuntimeError("このフォルダーは別のウィンドウで開かれています。先にそちらを閉じてください。")
            project = Project(root, default_settings=self.read_settings())
            project.save()
        except Exception as error:
            if new_lock is not None and not same_project:
                new_lock.unlock()
            QMessageBox.critical(self, "フォルダーを開けません", str(error))
            return
        if self.project_lock is not None and not same_project:
            self.project_lock.unlock()
        self.project_lock = new_lock
        self.thumb_timer.stop()
        self.save_timer.stop()
        self.project = project
        self.current_key = None
        self.items.clear()
        self.list.clear()
        self.folder_label.setText(str(root))
        self.apply_settings(project.settings)
        for key in project.records:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(250, 94))
            self.list.addItem(item)
            self.items[key] = item
            self.update_item(key)
        self.thumbnails = list(self.items)
        self.thumb_timer.start(10)
        self.settings_changed()
        self.refresh_filter()
        self.update_count()
        self.show_current()
        if project.scan_errors:
            QMessageBox.warning(self, "読み込めない画像", "\n".join(project.scan_errors[:10]))

    def read_settings(self) -> Settings:
        return Settings(target=self.target.currentData(), format=self.output_format.currentData(),
                        trigger=self.trigger.text(), trigger_source=self.trigger_source.currentData(),
                        trigger_length=self.trigger_length.value(), trigger_unit=self.trigger_unit.currentData(),
                        trigger_separators=self.trigger_separators.text(), include_identity=True,
                        model=self.model.currentData(), gpu_layers=self.layers.value(), max_edge=self.edge.currentData())

    def apply_settings(self, settings: Settings):
        self.loading = True
        for box, value in [(self.target, settings.target), (self.output_format, settings.format),
                           (self.model, settings.model), (self.edge, settings.max_edge),
                           (self.trigger_source, settings.trigger_source), (self.trigger_unit, settings.trigger_unit)]:
            box.setCurrentIndex(max(0, box.findData(value)))
        self.trigger.setText(settings.trigger)
        self.trigger_length.setValue(settings.trigger_length)
        self.trigger_separators.setText(settings.trigger_separators)
        self.layers.setValue(settings.gpu_layers)
        self.loading = False

    def load_thumbnails(self):
        for _ in range(min(8, len(self.thumbnails))):
            key = self.thumbnails.pop(0)
            pixmap = self.pixmap(key, QSize(88, 88))
            self.items[key].setIcon(QIcon(pixmap))
        if not self.thumbnails:
            self.thumb_timer.stop()

    def pixmap(self, key: str, size: QSize) -> QPixmap:
        reader = QImageReader(str(self.project.root / key))
        reader.setAutoTransform(True)
        source_size = reader.size()
        if source_size.isValid():
            reader.setScaledSize(source_size.scaled(size, Qt.AspectRatioMode.KeepAspectRatio))
        return QPixmap.fromImage(reader.read())

    def settings_changed(self, *_):
        if self.target.currentData() == "character":
            self.mode_hint.setText("見える外見を省略せず、人物ごとの特徴を対応させます。判別できない色は推測しません。")
        else:
            self.mode_hint.setText("画材・筆致・配色・画風の記述を省き、被写体や構図を記述します。")
        filename_trigger = self.trigger_source.currentData() == "filename"
        self.trigger.setEnabled(not filename_trigger)
        self.trigger_length.setEnabled(filename_trigger)
        self.trigger_unit.setEnabled(filename_trigger)
        self.trigger_separators.setEnabled(filename_trigger and self.trigger_unit.currentData() == "words")
        self.update_trigger_preview()
        if self.loading:
            return
        if self.project is not None:
            self.project.settings = self.read_settings()
        self.save_timer.start(400)

    def update_trigger_preview(self):
        settings = Settings(trigger=self.trigger.text(), trigger_source=self.trigger_source.currentData(),
                            trigger_length=self.trigger_length.value(), trigger_unit=self.trigger_unit.currentData(),
                            trigger_separators=self.trigger_separators.text())
        filename = self.current_key or "akari_school_001.png"
        try:
            trigger = resolve_trigger(settings, filename)
            prefix = Path(filename).name + " → " if settings.trigger_source == "filename" else "共通 → "
            self.trigger_preview.setText(prefix + (trigger or "（トリガーなし）") + "  ·  既存キャプションへの反映はJSONから再生成")
        except ValueError as error:
            self.trigger_preview.setText(str(error))

    def selected_keys(self) -> list[str]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems() if not i.isHidden()]

    def select_image(self, current, previous):
        self.current_key = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.show_current()

    def show_current(self):
        self.loading = True
        self.update_trigger_preview()
        if self.project is not None and self.current_key in self.project.records:
            record = self.project.records[self.current_key]
            self.editor.setPlainText(record.caption)
            self.analysis_view.setPlainText(json.dumps({"analysis": record.analysis, "error": record.error,
                                                       "history": record.history}, ensure_ascii=False, indent=2))
            self.file_label.setText(record.path + "  ·  " + STATUS.get(record.status, record.status)
                                    + ("  ·  手動編集済み" if record.edited else ""))
            image = self.pixmap(record.path, QSize(740, 250))
            self.image_label.setPixmap(image)
            if image.isNull():
                self.image_label.setText("画像を表示できません")
        else:
            self.editor.clear()
            self.analysis_view.clear()
            self.file_label.clear()
            self.image_label.clear()
            self.image_label.setText("画像を選択してください")
        self.loading = False

    def editor_changed(self):
        if self.loading or self.project is None or self.current_key is None:
            return
        self.project.edit(self.current_key, self.editor.toPlainText())
        self.update_item(self.current_key)
        self.update_count()
        self.save_timer.start(400)

    def update_item(self, key):
        record = self.project.records[key]
        self.items[key].setText(f"{key}\n{STATUS.get(record.status, record.status)}" + (" · 編集済み" if record.edited else ""))
        self.items[key].setToolTip(record.error or record.path)

    def refresh_filter(self):
        if self.project is None:
            return
        value = self.filter.currentData()
        for key, item in self.items.items():
            record = self.project.records[key]
            visible = value == "all" or (record.edited if value == "edited" else record.status == value)
            item.setHidden(not visible)

    def update_count(self):
        if self.project is not None:
            records = list(self.project.records.values())
            self.count_label.setText(f"{len(records)} 枚  ·  解析済み {sum(r.analysis is not None for r in records)}"
                                    f"  ·  エラー {sum(r.status == 'error' for r in records)}"
                                    f"  ·  編集済み {sum(r.edited for r in records)}  |  編集はJSONへ自動保存、TXTは出力ボタンで保存")

    def busy(self, value):
        for control in (self.open_button, self.settings_box, self.edit_box, self.pending_button, self.force_button, self.all_button, self.editor):
            control.setEnabled(not value)
        self.cancel_button.setEnabled(value)

    def start_analysis(self, force: bool, all_records: bool = False):
        if self.project is None or self.worker is not None:
            return
        self.settings_changed()
        if not self.safe_save():
            return
        keys = self.selected_keys() if force and not all_records else list(self.project.records)
        jobs = [(key, self.project.records[key].fingerprint) for key in keys
                if self.project.records[key].status != "missing" and
                (force or self.project.records[key].analysis is None or self.project.records[key].status == "error")]
        if not jobs:
            self.statusBar().showMessage("対象の画像がありません。選択画像の再解析では画像を選択してください。")
            return
        try:
            for key, _ in jobs:
                resolve_trigger(self.project.settings, key)
        except ValueError as error:
            QMessageBox.warning(self, "トリガーを確認してください", str(error))
            return
        self.worker = AnalysisWorker(self.project.root, jobs, self.project.settings)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.result.connect(self.analysis_result)
        self.worker.failure.connect(lambda text: QMessageBox.critical(self, "解析を開始できません", text))
        self.worker.finished.connect(self.analysis_finished)
        self.busy(True)
        self.worker.start()

    def analysis_result(self, key: str, event: dict):
        record = self.project.records[key]
        kind = event["event"]
        if kind == "started":
            record.status = "running"
        else:
            record.history.append({"at": now(), "previous_caption": record.caption, **event})
            if kind == "success":
                record.analysis = event["analysis"]
                record.status, record.error = "done", ""
                if not record.edited or self.allow_edited.isChecked():
                    record.caption = render(record.analysis, self.project.settings, record.path)
                    record.edited = False
            else:
                record.status, record.error = "error", event["error"]
        self.safe_save()
        self.update_item(key)
        self.update_count()
        self.refresh_filter()
        if key == self.current_key:
            self.show_current()

    def cancel_analysis(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("中止を受付しました。ダウンロードは取得済み部分を保持し、解析は現在の1枚の完了後に停止します。")

    def analysis_finished(self):
        worker = self.worker
        worker.wait()
        self.worker = None
        self.busy(False)
        for record in self.project.records.values():
            if record.status == "running":
                record.status = "pending"
                self.update_item(record.path)
        self.safe_save()
        worker.deleteLater()
        self.update_count()
        self.statusBar().showMessage("処理を終了しました。結果はJSONへ保存されています。")
        if self.close_requested:
            self.close()

    def rebuild(self, all_records: bool):
        if self.project is None:
            return
        try:
            keys = list(self.project.records) if all_records else self.selected_keys()
            count = self.project.regenerate(keys, self.allow_edited.isChecked())
            for key in keys:
                self.update_item(key)
            self.show_current()
            self.update_count()
            self.statusBar().showMessage(f"JSONから{count}枚を再生成しました。画像の再解析は行っていません。")
        except Exception as error:
            QMessageBox.critical(self, "再生成できません", str(error))

    def replace(self, all_records: bool):
        if self.project is None or not self.find_text.text():
            return
        keys = list(self.project.records) if all_records else self.selected_keys()
        count = 0
        for key in keys:
            record = self.project.records[key]
            text = record.caption.replace(self.find_text.text(), self.replace_text.text())
            if text != record.caption:
                self.project.edit(key, text)
                count += 1
                self.update_item(key)
        self.safe_save()
        self.show_current()
        self.update_count()
        self.statusBar().showMessage(f"{count}枚のキャプションを置換しました。変更前の内容はJSON履歴に残っています。")

    def export(self):
        if self.project is None or not self.safe_save():
            return
        try:
            written, skipped = self.project.export(self.overwrite_txt.isChecked())
            self.statusBar().showMessage(f"UTF-8 TXTを{written}件出力しました。既存TXTのスキップ: {skipped}件")
        except Exception as error:
            QMessageBox.critical(self, "出力できません", str(error))

    def closeEvent(self, event: QCloseEvent):
        if self.worker is not None:
            self.close_requested = True
            self.cancel_analysis()
            event.ignore()
            return
        if self.safe_save():
            if self.project_lock is not None:
                self.project_lock.unlock()
                self.project_lock = None
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    configure_app(app)
    window = MainWindow()
    if len(sys.argv) > 1:
        window.load_project(Path(sys.argv[1]))
    window.show()
    sys.exit(app.exec())
