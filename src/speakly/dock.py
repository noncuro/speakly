"""macOS Dock identity — set app name and icon at runtime."""

from __future__ import annotations

import sys


def configure_dock_name() -> None:
    """Override Dock name from 'python3.11' to 'Speakly'.

    Must be called BEFORE QApplication() is created.
    Uses NSBundle to patch CFBundleName in the process Info.plist.
    """
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = "Speakly"
    except Exception:
        pass


def configure_dock_icon() -> None:
    """Render a speaker icon and set it as the Dock icon.

    Must be called AFTER QApplication() is created (needs QPainter).
    Renders a 512x512 icon: blue Catppuccin gradient rounded-rect background
    with a white speaker and 3 sound-wave arcs.
    """
    if sys.platform != "darwin":
        return
    try:
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QRect, QRectF, Qt
        from PyQt6.QtGui import (
            QColor,
            QConicalGradient,
            QLinearGradient,
            QPainter,
            QPainterPath,
            QPen,
            QPixmap,
        )

        size = 512
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Background: Catppuccin blue gradient rounded square ---
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, size, size), 100, 100)

        gradient = QLinearGradient(QPoint(0, 0), QPoint(size, size))
        gradient.setColorAt(0.0, QColor("#89b4fa"))  # Catppuccin blue
        gradient.setColorAt(1.0, QColor("#74c7ec"))  # Catppuccin sapphire
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        painter.drawPath(bg_path)

        # --- Speaker body (white) ---
        white = QColor("#ffffff")
        painter.setBrush(white)
        painter.setPen(QPen(QColor(0, 0, 0, 0)))

        # Speaker rectangle (left part)
        speaker_path = QPainterPath()
        sx, sy = 130, 190
        sw, sh = 70, 132
        speaker_path.addRect(QRectF(sx, sy, sw, sh))

        # Speaker cone (trapezoid via polygon)
        cone_path = QPainterPath()
        cone_path.moveTo(sx + sw, sy)
        cone_path.lineTo(sx + sw + 100, sy - 60)
        cone_path.lineTo(sx + sw + 100, sy + sh + 60)
        cone_path.lineTo(sx + sw, sy + sh)
        cone_path.closeSubpath()

        painter.drawPath(speaker_path)
        painter.drawPath(cone_path)

        # --- Sound wave arcs ---
        pen = QPen(white, 22)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 0, 0, 0))

        cx = sx + sw + 100  # arc center x (tip of cone)
        cy = sy + sh // 2   # arc center y

        for i, radius in enumerate([70, 120, 170]):
            rect = QRect(cx - radius, cy - radius, radius * 2, radius * 2)
            painter.drawArc(rect, -45 * 16, 90 * 16)  # 90° arc centered on right

        painter.end()

        # --- Convert QPixmap → PNG bytes → NSImage → Dock icon ---
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        png_bytes = bytes(buf.data())
        buf.close()

        from AppKit import NSApplication, NSImage
        from Foundation import NSData

        ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        ns_image = NSImage.alloc().initWithData_(ns_data)
        NSApplication.sharedApplication().setApplicationIconImage_(ns_image)
    except Exception:
        pass
