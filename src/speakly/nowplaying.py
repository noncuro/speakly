"""macOS Now Playing integration — media keys + Control Center widget."""

from __future__ import annotations

import sys
from typing import Callable


class NowPlayingBridge:
    """Bridges MPRemoteCommandCenter commands to player callbacks
    and updates MPNowPlayingInfoCenter with playback metadata."""

    def __init__(
        self,
        on_play: Callable[[], None],
        on_pause: Callable[[], None],
        on_toggle: Callable[[], None],
        on_skip_forward: Callable[[], None],
        on_skip_backward: Callable[[], None],
        on_seek: Callable[[float], None],
    ):
        from MediaPlayer import (
            MPNowPlayingInfoCenter,
            MPRemoteCommandCenter,
        )

        self._on_play = on_play
        self._on_pause = on_pause
        self._on_toggle = on_toggle
        self._on_skip_forward = on_skip_forward
        self._on_skip_backward = on_skip_backward
        self._on_seek = on_seek

        self._info_center = MPNowPlayingInfoCenter.defaultCenter()
        self._cmd_center = MPRemoteCommandCenter.sharedCommandCenter()

        self._title = "Speakly"
        self._duration = 0.0
        self._elapsed = 0.0
        self._rate = 1.0

        self._register_commands()

    def _register_commands(self):
        cmd = self._cmd_center

        cmd.playCommand().addTargetWithHandler_(self._handle_play)
        cmd.pauseCommand().addTargetWithHandler_(self._handle_pause)
        cmd.togglePlayPauseCommand().addTargetWithHandler_(self._handle_toggle)

        skip_fwd = cmd.skipForwardCommand()
        skip_fwd.setPreferredIntervals_([10.0])
        skip_fwd.addTargetWithHandler_(self._handle_skip_forward)

        skip_back = cmd.skipBackwardCommand()
        skip_back.setPreferredIntervals_([10.0])
        skip_back.addTargetWithHandler_(self._handle_skip_backward)

        cmd.changePlaybackPositionCommand().addTargetWithHandler_(self._handle_seek)

        # Disable track navigation (not applicable for single-item player)
        cmd.nextTrackCommand().setEnabled_(False)
        cmd.previousTrackCommand().setEnabled_(False)

    def _handle_play(self, event):
        self._on_play()
        return 0  # MPRemoteCommandHandlerStatusSuccess

    def _handle_pause(self, event):
        self._on_pause()
        return 0

    def _handle_toggle(self, event):
        self._on_toggle()
        return 0

    def _handle_skip_forward(self, event):
        self._on_skip_forward()
        return 0

    def _handle_skip_backward(self, event):
        self._on_skip_backward()
        return 0

    def _handle_seek(self, event):
        self._on_seek(event.positionTime())
        return 0

    def update_info(
        self,
        title: str | None = None,
        duration: float | None = None,
        elapsed: float | None = None,
        rate: float | None = None,
        playing: bool | None = None,
    ):
        """Update Now Playing info. Only non-None fields are changed."""
        from MediaPlayer import (
            MPMediaItemPropertyTitle,
            MPMediaItemPropertyPlaybackDuration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime,
            MPNowPlayingInfoPropertyPlaybackRate,
            MPMusicPlaybackStatePlaying,
            MPMusicPlaybackStatePaused,
        )

        if title is not None:
            self._title = title
        if duration is not None:
            self._duration = duration
        if elapsed is not None:
            self._elapsed = elapsed
        if rate is not None:
            self._rate = rate

        info = {
            MPMediaItemPropertyTitle: self._title,
            MPMediaItemPropertyPlaybackDuration: self._duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: self._elapsed,
            MPNowPlayingInfoPropertyPlaybackRate: self._rate if playing is not False else 0.0,
        }
        self._info_center.setNowPlayingInfo_(info)

        if playing is not None:
            state = MPMusicPlaybackStatePlaying if playing else MPMusicPlaybackStatePaused
            self._info_center.setPlaybackState_(state)

    def clear(self):
        """Remove from Now Playing on close."""
        from MediaPlayer import MPMusicPlaybackStatePaused

        self._info_center.setNowPlayingInfo_(None)
        self._info_center.setPlaybackState_(MPMusicPlaybackStatePaused)


def create_bridge(
    on_play: Callable[[], None],
    on_pause: Callable[[], None],
    on_toggle: Callable[[], None],
    on_skip_forward: Callable[[], None],
    on_skip_backward: Callable[[], None],
    on_seek: Callable[[float], None],
) -> NowPlayingBridge | None:
    """Create a NowPlayingBridge on macOS, return None on other platforms."""
    if sys.platform != "darwin":
        return None
    try:
        return NowPlayingBridge(
            on_play=on_play,
            on_pause=on_pause,
            on_toggle=on_toggle,
            on_skip_forward=on_skip_forward,
            on_skip_backward=on_skip_backward,
            on_seek=on_seek,
        )
    except Exception:
        return None
