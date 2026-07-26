# darat/ui/widgets/collapsible_section.py
"""
CollapsibleSection widget — Blender/Unity property inspector style panel section.
Header has native Qt arrow toggles (DownArrow/RightArrow) and 1-column form layout.
"""

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QToolButton,
    QLabel, QFormLayout, QLayout, QSizePolicy
)
from PySide6.QtCore import Qt


class CollapsibleSection(QWidget):
    """
    A collapsible property section with native Qt arrow header and 1-column form layout.
    
    Default state is EXPANDED.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title_text = title

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header tool button
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapsibleHeader")
        self._toggle_btn.setText(f"  {title}")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle_btn.toggled.connect(self._on_toggled)

        root_layout.addWidget(self._toggle_btn)

        # Content frame
        self._content_frame = QFrame()
        self._content_frame.setObjectName("collapsibleContent")

        self._form_layout = QFormLayout(self._content_frame)
        self._form_layout.setContentsMargins(12, 12, 12, 12)
        self._form_layout.setSpacing(8)
        self._form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        root_layout.addWidget(self._content_frame)

    def _on_toggled(self, checked: bool):
        self._content_frame.setVisible(checked)
        self._toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )

    def set_expanded(self, expanded: bool):
        self._toggle_btn.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self._toggle_btn.isChecked()

    @property
    def content_layout(self) -> QFormLayout:
        return self._form_layout

    def add_row(self, label: str | QWidget, field: QWidget = None, restart: bool = False, tooltip: str = ""):
        if field is not None:
            if isinstance(label, str):
                lbl = QLabel(label)
                lbl.setObjectName("formLabel")
                lbl.setFixedWidth(150)
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if restart:
                    lbl.setToolTip("Requires drone restart to take effect")
                if tooltip:
                    lbl.setToolTip(tooltip)
                self._form_layout.addRow(lbl, field)
            else:
                self._form_layout.addRow(label, field)

        else:
            if isinstance(label, str):
                lbl = QLabel(label)
                self._form_layout.addRow(lbl)
            else:
                self._form_layout.addRow(label)

    def add_widget(self, widget: QWidget):
        self._form_layout.addRow(widget)

    def add_layout(self, layout: QLayout):
        self._form_layout.addRow(layout)
