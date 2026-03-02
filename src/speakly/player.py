"""PyQt6 floating mini-player for TTS audio playback."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from speakly import bench
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
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
QLabel#status {
    font-size: 12px;
    color: #a6adc8;
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
QPushButton:disabled {
    background-color: #1e1e2e;
    color: #585b70;
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
QPushButton#play:disabled {
    background-color: #45475a;
    color: #585b70;
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
QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 2px;
    height: 4px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 2px;
}
"""


class MiniPlayer(QMainWindow):
    title_updated = pyqtSignal(str)
    audio_ready = pyqtSignal(str)
    chunk_ready = pyqtSignal(str)
    progressive_error = pyqtSignal(str)
    progressive_done = pyqtSignal(str)
    progressive_status = pyqtSignal(str)

    def __init__(
        self,
        initial_title: str = "",
        initial_speed: float = 1.0,
        audio_path: Path | None = None,
        progressive_mode: bool = False,
        bench_exit: bool = False,
        provider: str = "edge",
    ):
        super().__init__()
        self._drag_pos = None
        self._loading = audio_path is None
        self._progressive_mode = progressive_mode
        self._bench_exit = bench_exit
        self._provider = provider
        self._progressive_done_flag = False
        self._progressive_failed = False
        self._final_audio_loaded = False
        self._final_audio_path: str | None = None
        self._chunk_queue: deque[str] = deque()
        self._waiting_for_chunk = False
        self._pending_advance = False

        self._speed_index = 0
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

        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(0.8)
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._player.setPlaybackRate(SPEEDS[self._speed_index])

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        self._title_label = QLabel(initial_title or "Speakly")
        self._title_label.setObjectName("title")
        self._title_label.setMaximumWidth(360)
        top_row.addWidget(self._title_label, stretch=1)
        close_btn = QPushButton("\u2715")
        close_btn.setObjectName("close")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close)
        top_row.addWidget(close_btn)
        layout.addLayout(top_row)

        self._scrub_row = QHBoxLayout()
        self._status_label = QLabel("Generating speech...")
        self._status_label.setObjectName("status")
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)

        self._time_label = QLabel("0:00")
        self._time_label.setObjectName("time")
        self._time_label.setFixedWidth(36)
        self._scrub = QSlider(Qt.Orientation.Horizontal)
        self._scrub.setRange(0, 0)
        self._scrub.sliderMoved.connect(self._seek)
        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("time")
        self._duration_label.setFixedWidth(36)

        if self._loading and not self._progressive_mode:
            self._status_label.setText(f"Generating via {self._provider}...")
            self._scrub_row.addWidget(self._status_label, stretch=1)
            self._scrub_row.addWidget(self._progress, stretch=2)
            self._time_label.hide()
            self._scrub.hide()
            self._duration_label.hide()
        else:
            self._progress.hide()
            if self._progressive_mode:
                self._status_label.setText(f"Streaming via {self._provider}...")
                self._scrub_row.addWidget(self._status_label)
            else:
                self._status_label.hide()
            self._scrub_row.addWidget(self._time_label)
            self._scrub_row.addWidget(self._scrub, stretch=1)
            self._scrub_row.addWidget(self._duration_label)

        layout.addLayout(self._scrub_row)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._rew_btn = QPushButton("\u23ea")
        self._rew_btn.setFixedSize(36, 32)
        self._rew_btn.clicked.connect(lambda: self._skip(-10000))
        controls.addWidget(self._rew_btn)

        self._play_btn = QPushButton("\u25b6")
        self._play_btn.setObjectName("play")
        self._play_btn.setFixedSize(50, 36)
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        self._fwd_btn = QPushButton("\u23e9")
        self._fwd_btn.setFixedSize(36, 32)
        self._fwd_btn.clicked.connect(lambda: self._skip(10000))
        controls.addWidget(self._fwd_btn)

        controls.addSpacing(12)

        self._speed_btns: list[QPushButton] = []
        for i, spd in enumerate(SPEEDS):
            label = f"{spd:.0f}x" if spd == int(spd) else f"{spd}x"
            btn = QPushButton(label)
            btn.setFixedSize(40, 28)
            btn.clicked.connect(lambda checked, idx=i: self._set_speed(idx))
            self._speed_btns.append(btn)
            controls.addWidget(btn)

        controls.addStretch()

        vol = QSlider(Qt.Orientation.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(80)
        vol.setFixedWidth(60)
        vol.valueChanged.connect(lambda v: self._audio_output.setVolume(v / 100))
        controls.addWidget(vol)

        layout.addLayout(controls)

        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self.title_updated.connect(self._set_title)
        self.audio_ready.connect(self._on_audio_ready)
        self.chunk_ready.connect(self._on_chunk_ready)
        self.progressive_error.connect(self._on_progressive_error)
        self.progressive_done.connect(self._on_progressive_done)
        self.progressive_status.connect(self._on_progressive_status)

        self._update_speed_buttons()

        if self._loading:
            self._set_controls_enabled(False)
        else:
            self._player.setSource(QUrl.fromLocalFile(str(audio_path)))
            self._player.play()
            self._set_controls_enabled(True)

        if self._progressive_mode:
            self._scrub.setToolTip("Seeking unlocks after full audio is generated.")
            self._scrub.setEnabled(False)

    def _set_controls_enabled(self, enabled: bool):
        self._play_btn.setEnabled(enabled)
        self._rew_btn.setEnabled(enabled)
        self._fwd_btn.setEnabled(enabled)

        scrub_enabled = enabled
        if self._progressive_mode and not self._final_audio_loaded:
            scrub_enabled = False
            self._scrub.setToolTip("Seeking unlocks after full audio is generated.")
        elif scrub_enabled:
            self._scrub.setToolTip("")
        self._scrub.setEnabled(scrub_enabled)

    @pyqtSlot(str)
    def _on_audio_ready(self, path_str: str):
        if self._progressive_mode:
            return

        bench.mark_first_audio()

        self._loading = False
        self._status_label.hide()
        self._progress.hide()
        self._scrub_row.removeWidget(self._status_label)
        self._scrub_row.removeWidget(self._progress)
        self._time_label.show()
        self._scrub.show()
        self._duration_label.show()
        self._scrub_row.addWidget(self._time_label)
        self._scrub_row.addWidget(self._scrub, stretch=1)
        self._scrub_row.addWidget(self._duration_label)

        self._set_controls_enabled(True)
        self._player.setSource(QUrl.fromLocalFile(path_str))
        self._player.setPlaybackRate(SPEEDS[self._speed_index])
        self._player.play()

        if self._bench_exit:
            self._emit_bench_summary_and_exit()

    @pyqtSlot(str)
    def _on_chunk_ready(self, path_str: str):
        if not self._progressive_mode:
            self._on_audio_ready(path_str)
            return

        if self._loading:
            bench.mark_first_audio()
            self._loading = False
            self._set_controls_enabled(True)
            self._load_and_play(path_str)
            self._set_status_text(f"Streaming via {self._provider}")
            if self._bench_exit:
                self._emit_bench_summary_and_exit()
            return

        if self._waiting_for_chunk and self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self._waiting_for_chunk = False
            self._load_and_play(path_str)
            self._set_status_text(f"Streaming via {self._provider}")
            return

        self._chunk_queue.append(path_str)
        if self._waiting_for_chunk and not self._pending_advance:
            self._waiting_for_chunk = False
            self._pending_advance = True
            QTimer.singleShot(0, self._advance_progressive_chunk)

    @pyqtSlot(str)
    def _on_progressive_status(self, status: str):
        if not (self._progressive_mode and status):
            return
        # Map generic orchestrator keywords to provider-aware messages
        status_map = {
            "streaming": f"Streaming via {self._provider}",
            "streaming (rate-limited)": f"Streaming via {self._provider} (rate-limited)",
            "complete": f"Streaming complete ({self._provider})",
        }
        self._set_status_text(status_map.get(status, status))

    @pyqtSlot(str)
    def _on_progressive_error(self, message: str):
        if not self._progressive_mode:
            return

        self._progressive_failed = True
        self._set_status_text(f"Error: {message}")
        self._title_label.setText(f"Error: {message}")

        if self._loading:
            self._set_controls_enabled(False)
            return

        if not self._chunk_queue and self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self._player.stop()

    @pyqtSlot(str)
    def _on_progressive_done(self, path_str: str):
        if not self._progressive_mode:
            return

        self._progressive_done_flag = True
        self._final_audio_path = path_str
        self._set_status_text(f"Streaming complete ({self._provider})")

        if self._should_switch_to_final_now():
            QTimer.singleShot(0, self._switch_to_final_audio)

    def _load_and_play(self, path_str: str):
        self._player.setSource(QUrl.fromLocalFile(path_str))
        self._player.setPlaybackRate(SPEEDS[self._speed_index])
        self._player.play()

    def _set_status_text(self, text: str):
        if self._status_label.isHidden() and self._progressive_mode:
            self._status_label.show()
        self._status_label.setText(text)

    def _should_switch_to_final_now(self) -> bool:
        """Only switch when playback naturally reached a chunk boundary."""
        if self._loading or self._chunk_queue:
            return False
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return False
        if self._waiting_for_chunk:
            return True
        if self._player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
            return True
        return self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def _switch_to_final_audio(self):
        if not self._progressive_mode or not self._final_audio_path:
            return
        bench.mark("final_audio_switch")
        self._player.setSource(QUrl.fromLocalFile(self._final_audio_path))
        self._player.setPlaybackRate(SPEEDS[self._speed_index])
        self._final_audio_loaded = True
        self._set_controls_enabled(True)

    def _advance_progressive_chunk(self):
        self._pending_advance = False
        if not self._progressive_mode:
            return

        if self._chunk_queue:
            next_path = self._chunk_queue.popleft()
            self._waiting_for_chunk = False
            self._load_and_play(next_path)
            self._set_status_text(f"Streaming via {self._provider}")
            return

        if self._progressive_done_flag:
            self._switch_to_final_audio()
            return

        if self._progressive_failed:
            self._waiting_for_chunk = False
            self._player.stop()
            self._set_status_text("Generation failed.")
            return

        self._waiting_for_chunk = True
        bench.mark("buffering_wait")
        self._set_status_text(f"Buffering ({self._provider})...")

    def _emit_bench_summary_and_exit(self):
        """Emit JSON summary and quit (--bench-exit mode)."""
        first_audio = bench.get_first_audio_time()
        bench.summary_json(
            first_audio_s=round(first_audio, 3) if first_audio else None,
            total_s=round(bench.elapsed(), 3),
            progressive=self._progressive_mode,
        )
        QTimer.singleShot(100, self.close)

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
            btn.setStyleSheet(btn.styleSheet())
        self.setStyleSheet(STYLE)

    @pyqtSlot(str)
    def _set_title(self, title: str):
        self._title_label.setText(title)

    def _on_position(self, pos: int):
        self._scrub.setValue(pos)
        self._time_label.setText(self._fmt(pos))

        if (
            self._progressive_mode
            and not self._progressive_done_flag
            and self._chunk_queue
            and not self._pending_advance
            and self._player.duration() > 0
            and pos >= max(0, self._player.duration() - 120)
        ):
            self._pending_advance = True
            QTimer.singleShot(40, self._advance_progressive_chunk)

    def _on_duration(self, dur: int):
        self._scrub.setRange(0, dur)
        self._duration_label.setText(self._fmt(dur))

    def _on_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("\u23f8")
        else:
            self._play_btn.setText("\u25b6")

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._progressive_mode and not self._pending_advance:
            self._pending_advance = True
            QTimer.singleShot(40, self._advance_progressive_chunk)

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def closeEvent(self, event):
        self._player.stop()
        from PyQt6.QtWidgets import QApplication

        QApplication.instance().quit()

    def update_title(self, title: str):
        """Thread-safe title update — emits signal to update on GUI thread."""
        self.title_updated.emit(title)

    def load_audio(self, path: Path):
        """Thread-safe full-file load signal."""
        self.audio_ready.emit(str(path))

    def queue_chunk(self, path: Path):
        """Thread-safe progressive chunk enqueue."""
        self.chunk_ready.emit(str(path))

    def set_progressive_status(self, status: str):
        """Thread-safe progressive status update."""
        self.progressive_status.emit(status)

    def set_progressive_error(self, message: str):
        """Thread-safe progressive error signal."""
        self.progressive_error.emit(message)

    def mark_progressive_done(self, path: Path):
        """Thread-safe progressive completion signal."""
        self.progressive_done.emit(str(path))
