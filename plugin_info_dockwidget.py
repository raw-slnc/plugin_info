# -*- coding: utf-8 -*-
import html
import re
import unicodedata

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import pyqtSignal, Qt, QCoreApplication, QTimer, QDate, QEvent

from ._network_mixin import NetworkMixin
from ._table_mixin import TableMixin
from ._filter_mixin import FilterMixin
from ._settings_mixin import SettingsMixin
from ._plugin_manager_mixin import PluginManagerMixin


class PluginInfoDockWidget(
    NetworkMixin,
    TableMixin,
    FilterMixin,
    SettingsMixin,
    PluginManagerMixin,
    QtWidgets.QDockWidget,
):
    closingPlugin = pyqtSignal()

    HEADER_JA_MAP = {
        "name": "プラグイン名(属性)",
        "plugin_id": "プラグインID(属性)",
        "version": "バージョン(属性)",
        "about": "概要",
        "author_name": "作者名",
        "average_vote": "平均評価",
        "create_date": "作成日",
        "deprecated": "非推奨",
        "description": "説明",
        "downloads": "ダウンロード数",
        "experimental": "実験的版フラグ",
        "external_dependencies": "外部依存関係",
        "file_name": "ファイル名",
        "homepage": "ホームページ",
        "icon": "アイコンURL",
        "qgis_maximum_version": "対応QGIS最大バージョン",
        "qgis_minimum_version": "対応QGIS最小バージョン",
        "rating_votes": "評価投票数",
        "repository": "リポジトリURL",
        "server": "サーバープラグイン可否",
        "tags": "タグ",
        "tracker": "課題管理URL",
        "trusted": "信頼済みフラグ",
        "update_date": "更新日",
        "uploaded_by": "アップロード者",
    }

    _NAME_COLUMN = 0
    _ABOUT_DATA_ROLE = Qt.UserRole + 8
    _ABOUT_MAX_LINES = 5
    _ABOUT_ESTIMATE_LINES = 3
    _INSTALLED_DATA_ROLE = Qt.UserRole + 9

    def __init__(self, iface=None, parent=None):
        super(PluginInfoDockWidget, self).__init__(parent)
        self.iface = iface
        self.setWindowTitle(self.tr("Plugin Info Browser"))
        self._repo_urls = self._build_repository_urls()
        self._repo_try_index = 0
        self._plugins_reply = None
        self._details_reply = None
        self._details_plugin_id = None
        self._pending_mode = None
        self._plugins_cache = []
        self._about_source_text = ""
        self._rating_mode = "all"
        self._rating_value = 0.0
        self._network_timeout = QTimer(self)
        self._network_timeout.setSingleShot(True)
        self._network_timeout.timeout.connect(self._on_network_timeout)

        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(int(QtWidgets.QApplication.doubleClickInterval() * 0.2))
        self._clicked_item = None
        self._click_timer.timeout.connect(self._on_single_click_timeout)

        self._setup_ui()
        self._restore_filter_toggle_settings()
        self._restore_created_since_settings()
        self._favorites = set()
        self._load_favorites()

        self.fetch_plugins()

    def _setup_ui(self):
        main_widget = QtWidgets.QWidget()
        self.setWidget(main_widget)
        layout = QtWidgets.QVBoxLayout(main_widget)

        # --- Filter group ---
        filter_group = QtWidgets.QGroupBox(self.tr("Filters"))
        filter_group_layout = QtWidgets.QVBoxLayout(filter_group)

        # Search + created-since row
        search_grid_layout = QtWidgets.QGridLayout()
        left_search_layout = QtWidgets.QHBoxLayout()
        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText(self.tr("Search by name or author..."))
        left_search_layout.addWidget(QtWidgets.QLabel(self.tr("Filter:")))
        left_search_layout.addWidget(self.search_bar)
        search_grid_layout.addLayout(left_search_layout, 0, 0)

        right_created_layout = QtWidgets.QHBoxLayout()
        self.created_since_checkbox = QtWidgets.QCheckBox(self.tr("Created since"))
        self.created_since_checkbox.setChecked(False)
        right_created_layout.addWidget(self.created_since_checkbox)

        self.created_since_date_edit = QtWidgets.QDateEdit(QDate.currentDate())
        self.created_since_date_edit.setDisplayFormat("yyyy.MM.dd")
        self.created_since_date_edit.setCalendarPopup(True)
        self.created_since_date_edit.setEnabled(False)
        self.created_since_date_edit.setMinimumWidth(
            int(self.created_since_date_edit.sizeHint().width() * 1.2)
        )
        right_created_layout.addWidget(self.created_since_date_edit)

        self.show_favorites_button = QtWidgets.QPushButton(self.tr("Favorites"))
        self.show_favorites_button.setCheckable(True)
        right_created_layout.addWidget(self.show_favorites_button)
        right_created_layout.addStretch(1)
        search_grid_layout.addLayout(right_created_layout, 0, 1)
        search_grid_layout.setColumnStretch(0, 9)
        search_grid_layout.setColumnStretch(1, 11)
        filter_group_layout.addLayout(search_grid_layout)

        # Button rows
        button_grid_layout = QtWidgets.QGridLayout()

        # Exclude controls (left column)
        exclude_controls_layout = QtWidgets.QHBoxLayout()
        self.exclude_experimental_button = QtWidgets.QPushButton(self.tr("Exclude experimental"))
        self.exclude_experimental_button.setCheckable(True)
        self.exclude_experimental_button.setChecked(False)
        self.exclude_experimental_button.setStyleSheet(
            "QPushButton:checked { background-color: rgb(242, 250, 235); }"
        )
        exclude_controls_layout.addWidget(self.exclude_experimental_button)

        self.exclude_deprecated_button = QtWidgets.QPushButton(self.tr("Exclude deprecated"))
        self.exclude_deprecated_button.setCheckable(True)
        self.exclude_deprecated_button.setChecked(False)
        self.exclude_deprecated_button.setStyleSheet(
            "QPushButton:checked { background-color: rgb(255, 240, 240); }"
        )
        exclude_controls_layout.addWidget(self.exclude_deprecated_button)
        exclude_controls_layout.addStretch(1)
        button_grid_layout.addLayout(exclude_controls_layout, 0, 0)

        # Min version combo (right column)
        minver_controls_layout = QtWidgets.QHBoxLayout()
        self.qgis_min_version_combo = QtWidgets.QComboBox()
        self.qgis_min_version_combo.addItem(self.tr("All QGIS min versions"), "")
        minver_controls_layout.addWidget(QtWidgets.QLabel(self.tr("QGIS min:")))
        minver_controls_layout.addWidget(self.qgis_min_version_combo)
        self.qgis_min_ltr_button = QtWidgets.QPushButton(self.tr("LTR"))
        self.qgis_min_ltr_button.setCheckable(True)
        self.qgis_min_ltr_button.setChecked(False)
        self.qgis_min_ltr_button.setStyleSheet(
            "QPushButton:checked { background-color: #2ecc40; color: white; font-weight: bold; }"
        )
        minver_controls_layout.addWidget(self.qgis_min_ltr_button)
        minver_controls_layout.addStretch(1)
        button_grid_layout.addLayout(minver_controls_layout, 0, 1)

        # Rating controls (left column)
        setting_controls_layout = QtWidgets.QHBoxLayout()
        setting_controls_layout.addWidget(QtWidgets.QLabel(self.tr("Rating:")))
        self.rating_filter_combo = QtWidgets.QComboBox()
        for label, mode, value in [
            ("All Ratings", "all", 0.0),
            ("4.5+", "min", 4.5),
            ("4.0+", "min", 4.0),
            ("3.0+", "min", 3.0),
            ("2.0+", "min", 2.0),
            ("1.0+", "min", 1.0),
            ("1.0-", "max", 1.0),
            ("2.0-", "max", 2.0),
            ("3.0-", "max", 3.0),
            ("4.5-", "max", 4.5),
        ]:
            self.rating_filter_combo.addItem(self.tr(label), (mode, float(value)))
        setting_controls_layout.addWidget(self.rating_filter_combo)
        self.only_experimental_button = QtWidgets.QPushButton(self.tr("Only experimental"))
        self.only_experimental_button.setCheckable(True)
        self.only_experimental_button.setChecked(False)
        self.only_experimental_button.setStyleSheet(
            "QPushButton:checked { background-color: rgb(242, 250, 235); }"
        )
        setting_controls_layout.addWidget(self.only_experimental_button)
        setting_controls_layout.addStretch(1)
        button_grid_layout.addLayout(setting_controls_layout, 1, 0)
        button_grid_layout.addWidget(QtWidgets.QWidget(), 2, 0)

        # Category + close (right column)
        category_controls_layout = QtWidgets.QHBoxLayout()
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.addItem(self.tr("All categories"), "")
        category_controls_layout.addWidget(QtWidgets.QLabel(self.tr("Category:")))
        category_controls_layout.addWidget(self.category_combo)
        self.close_button = QtWidgets.QPushButton(self.tr("Close"))
        category_controls_layout.addWidget(self.close_button)
        category_controls_layout.addStretch(1)
        button_grid_layout.addLayout(category_controls_layout, 1, 1)
        button_grid_layout.setColumnStretch(0, 1)
        button_grid_layout.setColumnStretch(1, 1)

        # Uniform button sizing
        filter_buttons = [
            self.exclude_experimental_button,
            self.exclude_deprecated_button,
            self.only_experimental_button,
        ]
        uniform_h = max(btn.sizeHint().height() for btn in filter_buttons)
        for btn in filter_buttons:
            btn.setFixedHeight(uniform_h)
        uniform_w = max(btn.sizeHint().width() for btn in filter_buttons)
        for btn in filter_buttons:
            btn.setFixedWidth(uniform_w)

        filter_group_layout.addLayout(button_grid_layout)
        layout.addWidget(filter_group)

        # --- Plugin table ---
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            self.tr("Name"), self.tr("plugin_id"), self.tr("Version"),
            self.tr("Download"), self.tr("Rating"), self.tr("Author")
        ])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMouseTracking(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        # --- About panel ---
        info_group2 = QtWidgets.QGroupBox(self.tr("About Plugin"))
        info_layout2 = QtWidgets.QVBoxLayout(info_group2)
        info_layout2.setContentsMargins(8, 8, 8, 8)
        info_layout2.setSpacing(6)
        self.about_label = QtWidgets.QLabel(self.tr("Select a plugin to show the about text."))
        self.about_label.setWordWrap(True)
        self.about_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.about_label.setTextFormat(Qt.PlainText)
        self.about_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._sync_about_label_height()
        info_layout2.addWidget(self.about_label)
        about_link_row = QtWidgets.QHBoxLayout()
        about_link_row.addStretch(1)
        self.about_open_link = QtWidgets.QLabel("<a href='open'>[Open Developer Page]</a>")
        self.about_open_link.setTextFormat(Qt.RichText)
        self.about_open_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.about_open_link.setOpenExternalLinks(False)
        self.about_open_link.linkActivated.connect(self._on_open_dev_page_link_activated)
        self.about_open_link.setEnabled(False)
        about_link_row.addWidget(self.about_open_link)
        info_layout2.addLayout(about_link_row)
        layout.addWidget(info_group2)

        # --- Info / legend panel ---
        info_group = QtWidgets.QGroupBox(self.tr("Information"))
        info_layout = QtWidgets.QVBoxLayout(info_group)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(6)

        legend_layout = QtWidgets.QHBoxLayout()
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.addWidget(QtWidgets.QLabel(self.tr("Legend:")))

        def _create_legend_label(text, color_style):
            lbl = QtWidgets.QLabel(text)
            lbl.setStyleSheet(
                f"background-color: {color_style}; border: 1px solid #ccc;"
                f" padding: 1px 4px; border-radius: 2px;"
            )
            return lbl

        legend_layout.addWidget(_create_legend_label(self.tr("Compatible"), "rgb(238, 246, 255)"))
        legend_layout.addWidget(_create_legend_label(self.tr("Experimental"), "rgb(242, 250, 235)"))
        legend_layout.addWidget(_create_legend_label(self.tr("Incompatible"), "rgb(255, 252, 232)"))
        legend_layout.addWidget(_create_legend_label(self.tr("Deprecated"), "rgb(255, 240, 240)"))
        legend_layout.addStretch(1)
        info_layout.addLayout(legend_layout)

        hints = QtWidgets.QLabel(
            self.tr(
                "<b>Double-Click 'Name':</b> Open Plugin Manager &amp; copy name to clipboard<br>"
                "<b>Right-Click:</b> Context Menu"
            )
        )
        hints.setStyleSheet("color: #666; font-size: 9pt;")
        hints.setWordWrap(True)
        info_layout.addWidget(hints)
        layout.addWidget(info_group)

        # --- Status / progress ---
        self.status_label = QtWidgets.QLabel(self.tr("Ready."))
        layout.addWidget(self.status_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # --- Debug headers panel ---
        self.debug_headers_panel = QtWidgets.QFrame()
        self.debug_headers_panel.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.debug_headers_panel.setVisible(False)
        debug_panel_layout = QtWidgets.QGridLayout(self.debug_headers_panel)
        debug_panel_layout.setContentsMargins(6, 6, 6, 6)
        self.debug_headers_label_left = QtWidgets.QLabel("")
        self.debug_headers_label_left.setWordWrap(True)
        self.debug_headers_label_left.setStyleSheet("color:#666; font-size:9pt;")
        self.debug_headers_label_left.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.debug_headers_label_left.setAlignment(Qt.AlignTop)
        self.debug_headers_label_right = QtWidgets.QLabel("")
        self.debug_headers_label_right.setWordWrap(True)
        self.debug_headers_label_right.setStyleSheet("color:#666; font-size:9pt;")
        self.debug_headers_label_right.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.debug_headers_label_right.setAlignment(Qt.AlignTop)
        debug_panel_layout.addWidget(self.debug_headers_label_left, 0, 0)
        debug_panel_layout.addWidget(self.debug_headers_label_right, 0, 1)
        layout.addWidget(self.debug_headers_panel)

        self.debug_headers_toggle_button = QtWidgets.QPushButton(self.tr("Show headers"))
        self.debug_headers_toggle_button.setCheckable(True)
        self.debug_headers_toggle_button.setChecked(False)
        layout.addWidget(self.debug_headers_toggle_button)

        # --- Signal connections ---
        self.search_bar.textChanged.connect(lambda: self.filter_table())
        self.exclude_experimental_button.toggled.connect(self._on_exclude_experimental_toggled)
        self.exclude_deprecated_button.toggled.connect(self._on_exclude_deprecated_toggled)
        self.only_experimental_button.toggled.connect(self._on_only_experimental_toggled)
        self.created_since_checkbox.toggled.connect(self._on_created_since_toggled)
        self.created_since_date_edit.dateChanged.connect(self._on_created_since_date_changed)
        self.show_favorites_button.toggled.connect(self._on_show_favorites_toggled)
        self.qgis_min_version_combo.currentIndexChanged.connect(lambda _: self.filter_table())
        self.qgis_min_ltr_button.toggled.connect(self._on_qgis_min_ltr_toggled)
        self.category_combo.currentIndexChanged.connect(lambda _: self.filter_table())
        self.rating_filter_combo.currentIndexChanged.connect(self._on_rating_combo_changed)
        self.close_button.clicked.connect(self.close)
        self.debug_headers_toggle_button.toggled.connect(self._toggle_debug_headers_panel)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.cellEntered.connect(self._on_table_cell_entered)
        self.table.itemDoubleClicked.connect(self._on_table_item_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.installEventFilter(self)

    def tr(self, message):
        return QCoreApplication.translate("PluginInfoDockWidget", message)

    # --- Click / keyboard event handlers ---

    def _on_single_click_timeout(self):
        self._clicked_item = None

    def _on_table_cell_clicked(self, row, column):
        return

    def _on_table_item_double_clicked(self, item):
        if item is None or item.column() != self._NAME_COLUMN:
            return
        self._click_timer.stop()
        self._clicked_item = None
        self.open_plugin_manager_for_item(item)

    def _on_table_cell_entered(self, _row, column):
        if column == self._NAME_COLUMN:
            self.table.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.table.viewport().setCursor(Qt.ArrowCursor)

    # --- About label ---

    def _sync_about_label_height(self):
        line_height = self.about_label.fontMetrics().lineSpacing()
        margins = self.about_label.contentsMargins()
        h = (line_height * self._ABOUT_MAX_LINES) + margins.top() + margins.bottom()
        self.about_label.setMinimumHeight(h)
        self.about_label.setMaximumHeight(h)

    @staticmethod
    def _char_display_units(ch):
        if ch.isspace():
            return 1
        east_asian = unicodedata.east_asian_width(ch)
        if east_asian in ("F", "W"):
            return 2
        return 1

    def _truncate_about_by_estimated_chars(self, text, width):
        decoded = html.unescape(str(text or ""))
        decoded = re.sub(r"<\s*br\s*/?\s*>", "\n", decoded, flags=re.IGNORECASE)
        normalized = " ".join(decoded.replace("\r\n", "\n").replace("\r", "\n").split())
        if not normalized:
            return ""

        metrics = self.about_label.fontMetrics()
        avg_char_px = max(1, metrics.averageCharWidth())
        chars_per_line = max(20, int(width / avg_char_px))
        budget_units = chars_per_line * self._ABOUT_ESTIMATE_LINES

        used_units = 0
        out_chars = []
        truncated = False
        for ch in normalized:
            ch_units = self._char_display_units(ch)
            if used_units + ch_units > budget_units:
                truncated = True
                break
            out_chars.append(ch)
            used_units += ch_units

        out = "".join(out_chars).rstrip()
        if truncated:
            out = f"{out} ..."
        return out

    def _refresh_about_label(self):
        text = self._about_source_text or self.tr("Select a plugin to show the about text.")
        width = max(1, self.about_label.contentsRect().width())
        self.about_label.setText(self._truncate_about_by_estimated_chars(text, width))

    def _on_table_selection_changed(self):
        selected_items = self.table.selectedItems()
        self.about_open_link.setEnabled(bool(selected_items))
        if not selected_items:
            self._about_source_text = self.tr("Select a plugin to show the about text.")
            self._refresh_about_label()
            return
        row = selected_items[0].row()
        name_item = self.table.item(row, self._NAME_COLUMN)
        about_text = ""
        if name_item is not None:
            about_text = str(name_item.data(self._ABOUT_DATA_ROLE) or "").strip()
        if not about_text:
            about_text = self.tr("No about text available for this plugin.")
        self._about_source_text = about_text
        self._refresh_about_label()

    def _on_open_dev_page_link_activated(self, _link):
        selected_items = self.table.selectedItems()
        if not selected_items:
            self.status_label.setText(self.tr("Please select a plugin first."))
            return
        row = selected_items[0].row()
        name_item = self.table.item(row, self._NAME_COLUMN)
        if name_item is None:
            self.status_label.setText(self.tr("Please select a plugin first."))
            return
        self.open_plugin_url(name_item)

    # --- Qt overrides ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_about_label_height()
        self._refresh_about_label()

    def eventFilter(self, source, event):
        if source == self.table and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                selected_items = self.table.selectedItems()
                if selected_items:
                    self.open_plugin_manager_for_item(selected_items[0])
                    return True
            elif event.key() == Qt.Key_Escape:
                self.table.clearSelection()
                return True
        return super().eventFilter(source, event)

    def _toggle_debug_headers_panel(self, checked):
        self.debug_headers_panel.setVisible(bool(checked))
        if checked:
            self.debug_headers_toggle_button.setText(self.tr("Hide headers"))
        else:
            self.debug_headers_toggle_button.setText(self.tr("Show headers"))

    def closeEvent(self, _event):
        self._save_filter_toggle_settings()
        self._save_created_since_settings()
        if self._plugins_reply is not None:
            self._plugins_reply.abort()
            self._plugins_reply.deleteLater()
            self._plugins_reply = None
        if self._details_reply is not None:
            self._details_reply.abort()
            self._details_reply.deleteLater()
            self._details_reply = None
