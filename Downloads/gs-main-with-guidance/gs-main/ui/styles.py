STYLESHEET = """
QMainWindow {
    background-color: #1e2a38;
}
QTabWidget::pane {
    border: 1px solid #2a3a4a;
    background: #141c26;
}
QTabBar::tab {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2a3a4a, stop:1 #1a2632);
    color: #8a9aaa;
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-weight: bold;
    font-size: 12px;
    min-width: 60px;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3a6a8a, stop:1 #2a4a6a);
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #2a3a4a;
    border-radius: 4px;
    margin-top: 12px;       /* increased for title visibility */
    padding-top: 8px;       /* increased for title visibility */
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1a2632, stop:1 #141c26);
    color: #c0d0e0;
    font-size: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 8px;
    color: #6a9ac0;
    font-weight: bold;
    font-size: 12px;
    background: transparent;
}
QLabel {
    color: #d0dce8;
    font-size: 12px;
}
QLabel#value {
    color: #6bc9ff;
    font-weight: bold;
    background-color: rgba(0, 20, 40, 0.6);
    padding: 1px 4px;
    border-radius: 2px;
    font-size: 12px;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #2a4a6a, stop:1 #1a2a3a);
    color: #d0e0f0;
    border: 1px solid #3a5a7a;
    border-radius: 4px;
    padding: 4px 12px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3a6a8a, stop:1 #2a4a6a);
    border: 1px solid #5a8aaa;
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #1a3a5a, stop:1 #0a1a2a);
}
QComboBox {
    background: #1a2632;
    color: #c0d0e0;
    border: 1px solid #2a4a5a;
    border-radius: 4px;
    padding: 4px;
    font-size: 12px;
}
QComboBox:hover {
    border: 1px solid #3a6a8a;
}
QLabel#status_ok {
    color: #60c090;
    font-weight: bold;
}
QLabel#status_warn {
    color: #f0a030;
    font-weight: bold;
}
QLabel#status_error {
    color: #e06050;
    font-weight: bold;
}
"""