"""PyQt6 floating mini-player for TTS audio playback."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

SPEEDS = [1.0, 1.5, 2.0, 3.0]

STYLE = """
QMainWindow {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 12px;
}
QLabel {
    color: #cdd6f4;
    font-size: 13px;
}
QLabel#title {
    font-size: 14px;
    font-weight: bold;
    color: #cdd6f4;
}
QLabel#time {
    font-size: 11px;
    color: #a6adc8;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton#play {
    background-color: #89b4fa;
    color: #1e1e2e;
    padding: 8px 16px;
    font-size: 15px;
}
QPushButton#play:hover {
    background-color: #74c7ec;
}
QPushButton#speed_active {
    background-color: #a6e3a1;
    color: #1e1e2e;
}
QPushButton#close {
    background-color: transparent;
    color: #6c7086;
    padding: 2px 6px;
    font-size: 14px;
}
QPushButton#close:hover {
    color: #f38ba8;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #45475a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #89b4fa;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #89b4fa;
    border-radius: 2px;
}
"""


class MiniPlayer(QMainWindow):
    title_updated = pyqtSignal(str)

    def __init__(self, audio_path: Path, initial_title: str = "", initial_speed: float = 1.0):
        super().__init__()
        self._drag_pos = None
        self._speed_index = 0
        # Find closest speed index to initial_speed
        for i, s in enumerate(SPEEDS):
            if abs(s - initial_speed) < abs(SPEEDS[self._speed_index] - initial_speed):
                self._speed_index = i

        self.setWindowTitle("Speakly")
        self.setFixedSize(420, 140)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(STYLE)

        # Audio setup
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(0.8)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile(str(audio_path)))
        self._player.setPlaybackRate(SPEEDS[self._speed_index])

        # Build UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        # Top row: title + close
        top_row = QHBoxLayout()
        self._title_label = QLabel(initial_title or "Loading...")
        self._title_label.setObjectName("title")
        self._title_label.setMaximumWidth(360)
        top_row.addWidget(self._title_label, stretch=1)
        close_btn = QPushButton("\u2715")
        close_btn.setObjectName("close")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        # Scrub bar
        scrub_row = QHBoxLayout()
        self._time_label = QLabel("0:00")
        self._time_label.setObjectName("time")
        self._time_label.setFixedWidth(36)
        scrub_row.addWidget(self._time_label)
        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setRange(0, 0)
        self._scrub.sliderMoved.connect(self._seek)
        scrub_row.addWidget(self._scrub, stretch=1)
        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("time")
        self._duration_label.setFixedWidth(36)
        scrub_row.addWidget(self._duration_label)
        layout.addLayout(scrub_row)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(8)

        rew_btn = QPushButton("\u23ea")
        rew_btn.setFixedSize(36, 32)
        rew_btn.clicked.connect(lambda: self._skip(-10000))
        controls.addWidget(rew_btn)

        self._play_btn = QPushButton("\u25b6")
        self._play_btn.setObjectName("play")
        self._play_btn.setFixedSize(50, 36)
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        fwd_btn = QPushButton("\u23e9")
        fwd_btn.setFixedSize(36, 32)
        fwd_btn.clicked.connect(lambda: self._skip(10000))
        controls.addWidget(fwd_btn)

        controls.addSpacing(12)

        # Speed buttons
        self._speed_btns: list[QPushButton] = []
        for i, spd in enumerate(SPEEDS):
            label = f"{spd:.0f}x" if spd == int(spd) else f"{spd}x"
            btn = QPushButton(label)
            btn.setFixedSize(40, 28)
            btn.clicked.connect(lambda checked, idx=i: self._set_speed(idx))
            self._speed_btns.append(btn)
            controls.addWidget(btn)

        controls.addStretch()

        # Volume
        vol = QSlider(Qt.Orientation.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(80)
        vol.setFixedWidth(60)
        vol.valueChanged.connect(lambda v: self._audio_output.setVolume(v / 100))
        controls.addWidget(vol)

        layout.addLayout(controls)

        # Signals
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self.title_updated.connect(self._set_title)

        self._update_speed_buttons()

        # Auto-play
        self._player.play()

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _skip(self, ms: int):
        pos = max(0, self._player.position() + ms)
        self._player.setPosition(min(pos, self._player.duration()))

    def _seek(self, pos: int):
        self._player.setPosition(pos)

    def _set_speed(self, idx: int):
        self._speed_index = idx
        self._player.setPlaybackRate(SPEEDS[idx])
        self._update_speed_buttons()

    def _update_speed_buttons(self):
        for i, btn in enumerate(self._speed_btns):
            if i == self._speed_index:
                btn.setObjectName("speed_active")
            else:
                btn.setObjectName("")
            btn.setStyleSheet(btn.styleSheet())  # force re-style
            # Re-apply the main stylesheet to pick up object name changes
        self.setStyleSheet(STYLE)

    @pyqtSlot(str)
    def _set_title(self, title: str):
        self._title_label.setText(title)

    def _on_position(self, pos: int):
        self._scrub.setValue(pos)
        self._time_label.setText(self._fmt(pos))

    def _on_duration(self, dur: int):
        self._scrub.setRange(0, dur)
        self._duration_label.setText(self._fmt(dur))

    def _on_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("\u23f8")
        else:
            self._play_btn.setText("\u25b6")

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    # Dragging
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def update_title(self, title: str):
        """Thread-safe title update — emits signal to update on GUI thread."""
        self.title_updated.emit(title)
