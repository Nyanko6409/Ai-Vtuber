"""AI VTuber - UI Theme and Styling Constants

Centralized color definitions and stylesheet fragments for consistent UI styling.
"""

# ================================================================================
# MAIN WINDOW COLORS (qt_main_window.py)
# ================================================================================

# Background colors
BG_BLACK = "#000000"  # Pure Black: Main window background, OpenGL clear color, Live2D widget
BG_DARK_GRAY = "rgba(25, 25, 35, 230)"  # Chat input field background
BG_LIGHTER_DARK_GRAY = "rgba(35, 35, 50, 240)"  # Chat input focused background
BG_TRANSPARENT = "transparent"  # Chat input container

# Button colors
BTN_BLUE = "rgba(50, 100, 200, 200)"  # Send button background
BTN_BLUE_HOVER = "rgba(70, 130, 230, 220)"  # Send button hover
BTN_BLUE_PRESSED = "rgba(40, 90, 180, 200)"  # Send button pressed
BTN_BLUE_GRAY_START = "rgba(60, 60, 90, 200)"  # Status bar buttons gradient start
BTN_BLUE_GRAY_END = "rgba(40, 40, 70, 200)"  # Status bar buttons gradient end

# Text colors
TEXT_WHITE = "white"  # Primary text, button text
TEXT_PLACEHOLDER = "rgba(180, 180, 200, 150)"  # Placeholder text in input fields
TEXT_FPS_LABEL = "#a0b0ff"  # FPS label, value labels
TEXT_MIC_ON = "#81C784"  # Green: Microphone ON indicator
TEXT_MIC_OFF = "#EF5350"  # Red: Microphone OFF indicator

# Border colors
BORDER_INPUT_DEFAULT = "rgba(100, 150, 255, 60)"  # Input field border default
BORDER_INPUT_FOCUSED = "rgba(120, 170, 255, 120)"  # Input field border focused

# Status bar colors
STATUS_BAR_BG_START = "rgba(20, 20, 30, 200)"  # Dark Blue-Gray Gradient start
STATUS_BAR_BG_MID = "rgba(30, 30, 45, 220)"  # Dark Blue-Gray Gradient middle
STATUS_BAR_BG_END = "rgba(20, 20, 30, 200)"  # Dark Blue-Gray Gradient end
STATUS_BAR_FPS_BG = "rgba(40, 40, 60, 180)"  # FPS counter container
STATUS_BAR_SEPARATOR = "rgba(100, 150, 255, 60)"  # Separator line


# ================================================================================
# SETTINGS DIALOG COLORS (pyside_settings.py)
# ================================================================================

# Background colors
SETTINGS_BG = "#1e1e2e"  # Dark Blue-Gray: Main dialog background, tab widget
SETTINGS_TAB_BG = "#2a2a3a"  # Medium Dark Gray: Tab buttons, group boxes
SETTINGS_TAB_SELECTED = "#4a4a6a"  # Lighter Gray: Selected tab
SETTINGS_TAB_HOVER = "#3a3a5a"  # Hover Gray: Hovered tab
SETTINGS_INPUT_BG = "#252535"  # Input Background: Text input fields
SETTINGS_BORDER = "#3b3b4f"  # Border Color: Borders, separators

# Button colors
SETTINGS_BTN_SAVE = "#6a80ff"  # Blue: Primary action button (Save)
SETTINGS_BTN_SAVE_HOVER = "#8a90ff"  # Lighter Blue: Save button hover
SETTINGS_BTN_CANCEL = "#4a60c0"  # Darker Blue: Cancel button
SETTINGS_BTN_CANCEL_HOVER = "#5a70d0"  # Medium Blue: Cancel button hover
SETTINGS_BTN_DISABLED = "#4a4a5a"  # Disabled Gray: Disabled buttons
SETTINGS_BTN_DISABLED_HOVER = "#5a5a6a"  # Disabled button hover

# Text colors
SETTINGS_TEXT_PRIMARY = "#ffffff"  # White: Primary text, labels
SETTINGS_TEXT_VALUE = "#a0b0ff"  # Light Blue: Value labels, titles
SETTINGS_TEXT_PLACEHOLDER = "#cccccc"  # Light Gray: Placeholder text


# ================================================================================
# COMMON STYLESHEETS
# ================================================================================

def get_chat_input_stylesheet() -> str:
    """Get the stylesheet for chat input field."""
    return f"""
        QLineEdit {{
            background-color: {BG_DARK_GRAY};
            color: {TEXT_WHITE};
            border: 1px solid {BORDER_INPUT_DEFAULT};
            border-radius: 8px;
            padding: 0 15px;
            font-size: 14px;
        }}
        QLineEdit:focus {{
            border: 1px solid {BORDER_INPUT_FOCUSED};
            background-color: {BG_LIGHTER_DARK_GRAY};
        }}
        QLineEdit::placeholder {{
            color: {TEXT_PLACEHOLDER};
        }}
    """


def get_chat_send_button_stylesheet() -> str:
    """Get the stylesheet for chat send button."""
    return f"""
        QPushButton {{
            background-color: {BTN_BLUE};
            border: none;
            border-radius: 8px;
            font-size: 16px;
            color: {TEXT_WHITE};
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {BTN_BLUE_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {BTN_BLUE_PRESSED};
        }}
    """


def get_status_bar_stylesheet() -> str:
    """Get the stylesheet for status bar."""
    return f"""
        #statusBar {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {STATUS_BAR_BG_START},
                stop:0.5 {STATUS_BAR_BG_MID},
                stop:1 {STATUS_BAR_BG_END});
            border-top: 1px solid {STATUS_BAR_SEPARATOR};
            border-bottom: none;
        }}
    """


def get_status_bar_fps_container_stylesheet() -> str:
    """Get the stylesheet for FPS counter container."""
    return f"""
        QWidget {{
            background-color: {STATUS_BAR_FPS_BG};
            border-radius: 8px;
            border: 1px solid {STATUS_BAR_SEPARATOR};
        }}
    """


def get_status_bar_icon_button_stylesheet() -> str:
    """Get the stylesheet for status bar icon buttons."""
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {BTN_BLUE_GRAY_START},
                stop:1 {BTN_BLUE_GRAY_END});
            border: 1px solid {STATUS_BAR_SEPARATOR};
            border-radius: 10px;
            font-size: 18px;
            color: {TEXT_WHITE};
            padding: 4px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(80, 80, 120, 220),
                stop:1 rgba(60, 60, 100, 220));
            border: 1px solid rgba(120, 170, 255, 100);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(50, 50, 80, 200),
                stop:1 rgba(30, 30, 60, 200));
            border: 1px solid rgba(80, 130, 235, 80);
            padding: 5px 3px 3px 5px;
        }}
    """


def get_settings_base_stylesheet() -> str:
    """Get the base stylesheet for settings dialog."""
    return f"""
        QDialog {{
            background-color: {SETTINGS_BG};
            color: {SETTINGS_TEXT_PRIMARY};
        }}
        QTabWidget::pane {{
            border: 1px solid {SETTINGS_BORDER};
            background-color: {SETTINGS_BG};
            border-radius: 8px;
        }}
        QTabBar::tab {{
            background-color: {SETTINGS_TAB_BG};
            color: {SETTINGS_TEXT_PRIMARY};
            padding: 10px 20px;
            margin: 2px;
            border-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background-color: {SETTINGS_TAB_SELECTED};
        }}
        QTabBar::tab:hover {{
            background-color: {SETTINGS_TAB_HOVER};
        }}
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {SETTINGS_BORDER};
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 10px;
            background-color: {SETTINGS_INPUT_BG};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: {SETTINGS_TEXT_VALUE};
        }}
        QLabel {{
            color: #e0e0e0;
            padding: 4px;
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {SETTINGS_TAB_BG};
            border: 1px solid {SETTINGS_BORDER};
            border-radius: 4px;
            padding: 6px;
            color: {SETTINGS_TEXT_PRIMARY};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1px solid {SETTINGS_BTN_SAVE};
        }}
        QSlider::groove:horizontal {{
            border: 1px solid {SETTINGS_BORDER};
            height: 8px;
            background: {SETTINGS_TAB_BG};
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {SETTINGS_BTN_SAVE};
            border: 1px solid {SETTINGS_BORDER};
            width: 18px;
            margin: -6px 0;
            border-radius: 9px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {SETTINGS_BTN_SAVE_HOVER};
        }}
        QCheckBox {{
            spacing: 8px;
            color: #e0e0e0;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {SETTINGS_BORDER};
            background-color: {SETTINGS_TAB_BG};
        }}
        QCheckBox::indicator:checked {{
            background-color: {SETTINGS_BTN_SAVE};
            border: 1px solid {SETTINGS_BTN_SAVE};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {SETTINGS_BTN_SAVE};
        }}
        QPushButton {{
            background-color: {SETTINGS_BTN_CANCEL};
            color: {SETTINGS_TEXT_PRIMARY};
            border: none;
            padding: 10px 24px;
            border-radius: 6px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {SETTINGS_BTN_CANCEL_HOVER};
        }}
        QPushButton:pressed {{
            background-color: #3a50b0;
        }}
        QPushButton#saveButton {{
            background-color: {SETTINGS_BTN_SAVE};
        }}
        QPushButton#saveButton:hover {{
            background-color: {SETTINGS_BTN_SAVE_HOVER};
        }}
        QPushButton#cancelButton {{
            background-color: {SETTINGS_BTN_DISABLED};
        }}
        QPushButton#cancelButton:hover {{
            background-color: {SETTINGS_BTN_DISABLED_HOVER};
        }}
        QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QScrollBar:vertical {{
            background: {SETTINGS_BG};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background: {SETTINGS_BORDER};
            border-radius: 6px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #4b4b5f;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
