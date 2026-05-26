"""
Reusable custom widgets: TempGauge, FanWidget, ModeButton, ColorSwatch.
"""

import math

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QPainter, QPen, QPainterPath, QBrush,
                         QLinearGradient, QRadialGradient)
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QSizePolicy,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
)

from gui import theme


class TempGauge(QWidget):
    """
    Circular arc gauge. 270° sweep, text centered in the widget.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._value = 0
        self.setFixedSize(140, 140)

    def setValue(self, value: int) -> None:
        self._value = max(0, min(value, 120))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        m = 16
        arc_rect = QRectF(m, m, w - m * 2, h - m * 2)

        # 270° arc: starts at 225° (bottom-left), sweeps counter-clockwise
        start  =  225 * 16
        full   = -270 * 16

        # Background arc — thin, neutral
        p.setPen(QPen(theme.qcolor("border"), 5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(arc_rect, start, full)

        # Value arc — thin, muted cool→warm ramp
        if self._value > 0:
            pct  = min(self._value / 100.0, 1.0)
            span = int(full * pct)
            p.setPen(QPen(theme.temp_qcolor(self._value), 5, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            p.drawArc(arc_rect, start, span)

        # Center: value text
        cx, cy = w / 2, h / 2
        from core.settings import use_fahrenheit
        if use_fahrenheit():
            disp = f"{int(self._value * 9 / 5 + 32)}°F"
        else:
            disp = f"{self._value}°"
        p.setPen(theme.qcolor("text"))
        p.setFont(QFont("Sans Serif", 21, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 45, cy - 22, 90, 36),
                   Qt.AlignmentFlag.AlignCenter, disp)

        # Center: label
        p.setPen(theme.qcolor("text_mute"))
        p.setFont(QFont("Sans Serif", 9))
        p.drawText(QRectF(cx - 30, cy + 16, 60, 18),
                   Qt.AlignmentFlag.AlignCenter,
                   self._label)

        p.end()


class FanWidget(QWidget):
    """
    Animated fan icon. Speed 0–100 → rotation speed.
    Draws 3 blades, rotates via QTimer.
    """

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._rpm   = 0
        self._angle = 0.0
        self.setFixedSize(100, 110)

        self._timer = QTimer(self)
        self._timer.setInterval(30)   # ~33 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def setRpm(self, rpm: int) -> None:
        self._rpm = rpm

    def _tick(self) -> None:
        # degrees per frame = rpm / 60 * 360 / 33fps ≈ rpm * 0.18
        speed = min(self._rpm / 3000.0, 1.0)
        self._angle = (self._angle + speed * 12.0) % 360.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, (h - 18) / 2

        radius = min(w, h - 18) / 2 - 6
        speed  = min(self._rpm / 3000.0, 1.0)
        blade_color = QColor(
            int(60 + 80 * speed),
            int(60 + 80 * (1 - speed * 0.5)),
            int(80 + 60 * (1 - speed)),
            220
        )

        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)

        # 3 blades at 120° apart
        for i in range(3):
            p.save()
            p.rotate(i * 120)
            path = QPainterPath()
            # Blade: an ellipse rotated 30°
            path.addEllipse(QRectF(2, -radius * 0.9, radius * 0.55, radius * 0.9))
            p.rotate(30)
            p.setBrush(QBrush(blade_color))
            p.setPen(QPen(blade_color.darker(130), 0.5))
            p.drawPath(path)
            p.restore()

        # Hub circle
        p.setBrush(QBrush(QColor(55, 55, 60)))
        p.setPen(QPen(QColor(80, 80, 85), 1))
        p.drawEllipse(QRectF(-6, -6, 12, 12))

        p.restore()

        # RPM label below
        p.setPen(QColor(140, 140, 145))
        p.setFont(QFont("Sans Serif", 9))
        p.drawText(QRectF(0, h - 18, w, 16),
                   Qt.AlignmentFlag.AlignCenter,
                   f"{self._label}  {self._rpm} RPM")

        p.end()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class ModeButton(QPushButton):
    """Styled mode button with active/inactive states."""

    def __init__(self, mode: str, label: str, parent=None):
        super().__init__(label, parent)
        self._mode   = mode
        self._active = False
        self.setMinimumHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()

    def _mode_color(self) -> str:
        from core.rgb import MODE_COLORS
        return f"#{MODE_COLORS.get(self._mode, '888888')}"

    def setActive(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._refresh()

    def refresh_color(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        color = theme.shade(self._mode_color())
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text')};
                    border: none;
                    border-bottom: 2px solid {color};
                    border-radius: 0;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.color('text_mute')};
                    border: none;
                    border-bottom: 2px solid transparent;
                    border-radius: 0;
                    font-size: 13px;
                    padding: 6px 4px;
                }}
                QPushButton:hover {{
                    color: {theme.color('text_dim')};
                }}
            """)


class UsageBar(QWidget):
    """Horizontal load bar: label | ████░░░ | pct  info"""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = QColor(color)
        self._pct = 0
        self._info = ""
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def update_value(self, pct: int, info: str = "") -> None:
        self._pct = max(0, min(pct, 100))
        self._info = info
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        label_w = 36
        pct_w = 34
        info_w = 90
        bar_x = label_w + 6
        bar_w = max(0, w - bar_x - pct_w - info_w - 8)
        bar_h = 5
        bar_y = (h - bar_h) / 2

        p.setPen(theme.qcolor("text_mute"))
        p.setFont(QFont("Sans Serif", 9))
        p.drawText(QRectF(0, 0, label_w, h),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._label)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("surface_2"))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2.5, 2.5)

        if self._pct > 0 and bar_w > 0:
            p.setBrush(self._color)
            p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w * self._pct / 100, bar_h), 2.5, 2.5)

        p.setPen(theme.qcolor("text"))
        p.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        p.drawText(QRectF(bar_x + bar_w + 6, 0, pct_w, h),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   f"{self._pct}%")

        if self._info:
            p.setPen(theme.qcolor("text_faint"))
            p.setFont(QFont("Sans Serif", 8))
            p.drawText(QRectF(bar_x + bar_w + pct_w + 10, 0, info_w, h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self._info)
        p.end()


class FanCurveChart(QWidget):
    """Live fan curve chart: configured curve + current operating point."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve_pts: list[tuple[int, float]] = []  # (temp, pct)
        self._idle_speed = 0.0
        self._cur_temp = 0
        self._cur_pct = 0.0
        self._mode_name = ""
        self.setMinimumHeight(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_curve(self, mode_name: str, temp_curve: list, speed_curve: list,
                  idle_speed: float = 0) -> None:
        self._mode_name = mode_name
        self._idle_speed = float(idle_speed)
        self._curve_pts = list(zip(temp_curve, speed_curve))
        self.update()

    def set_current(self, temp: int, pct: float = 0.0) -> None:
        self._cur_temp = temp
        self._cur_pct = pct
        self.update()

    def _interp_pct(self, temp: int) -> float:
        if not self._curve_pts:
            return self._idle_speed
        T_MIN = 20  # must match paintEvent
        t_first, s_first = self._curve_pts[0]
        # Below first curve point: interpolate (T_MIN, idle) → first point
        if temp <= t_first:
            if t_first <= T_MIN:
                return self._idle_speed
            frac = max(0.0, (temp - T_MIN) / (t_first - T_MIN))
            return self._idle_speed + (s_first - self._idle_speed) * frac
        # Above last curve point
        if temp >= self._curve_pts[-1][0]:
            return float(self._curve_pts[-1][1])
        # Interpolate between configured segments
        for i in range(len(self._curve_pts) - 1):
            t0, s0 = self._curve_pts[i]
            t1, s1 = self._curve_pts[i + 1]
            if t0 <= temp <= t1:
                return s0 + (s1 - s0) * (temp - t0) / (t1 - t0)
        return self._idle_speed

    def paintEvent(self, event):
        if not self._curve_pts:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        PAD_L, PAD_R, PAD_T, PAD_B = 30, 10, 6, 20
        cw = w - PAD_L - PAD_R
        ch = h - PAD_T - PAD_B
        T_MIN, T_MAX = 20, 100

        def px(temp, pct):
            x = PAD_L + (temp - T_MIN) / (T_MAX - T_MIN) * cw
            y = PAD_T + ch - pct / 100 * ch
            return QPointF(x, y)

        # Grid
        p.setPen(QPen(QColor(36, 36, 42), 1))
        for t in (40, 60, 80):
            pt = px(t, 0)
            p.drawLine(QPointF(pt.x(), PAD_T), QPointF(pt.x(), PAD_T + ch))
        for pct in (25, 50, 75):
            pt = px(T_MIN, pct)
            p.drawLine(QPointF(PAD_L, pt.y()), QPointF(PAD_L + cw, pt.y()))

        # Axis labels
        p.setPen(QColor(70, 70, 80))
        p.setFont(QFont("Sans Serif", 7))
        for t in (40, 60, 80):
            pt = px(t, 0)
            p.drawText(QRectF(pt.x() - 14, PAD_T + ch + 4, 28, 14),
                       Qt.AlignmentFlag.AlignCenter, f"{t}°")
        for pct in (0, 50, 100):
            pt = px(T_MIN, pct)
            p.drawText(QRectF(0, pt.y() - 7, PAD_L - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(pct))

        # Build extended curve: flat idle from T_MIN to first point, flat max after last
        ext = [(T_MIN, self._idle_speed)] + self._curve_pts + \
              [(T_MAX, self._curve_pts[-1][1] if self._curve_pts else self._idle_speed)]

        # Fill under curve
        fill = QPainterPath()
        fill.moveTo(px(ext[0][0], 0))
        for t, s in ext:
            fill.lineTo(px(t, s))
        fill.lineTo(px(ext[-1][0], 0))
        fill.closeSubpath()
        p.fillPath(fill, theme.qcolor("accent", 28))

        # Curve line
        path = QPainterPath()
        path.moveTo(px(ext[0][0], ext[0][1]))
        for t, s in ext[1:]:
            path.lineTo(px(t, s))
        p.setPen(QPen(theme.qcolor("accent"), 1.8,
                      Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

        # Config knot dots
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("accent"))
        for t, s in self._curve_pts:
            if T_MIN <= t <= T_MAX:
                p.drawEllipse(px(t, s), 3.5, 3.5)

        # Current operating point — always on the curve (interpolated)
        if self._cur_temp > 0 and self._curve_pts:
            dot_pct = self._interp_pct(self._cur_temp)
            pt = px(self._cur_temp, dot_pct)
            p.setBrush(QColor(255, 190, 0, 50))
            p.drawEllipse(pt, 9, 9)
            p.setBrush(QColor(255, 190, 0))
            p.drawEllipse(pt, 4.5, 4.5)

        p.end()


class FanCurveEditor(QWidget):
    """Interactive fan curve editor with draggable control points."""

    curve_changed = pyqtSignal(list, list)  # temp_curve, speed_curve (int lists)

    PAD_L, PAD_R, PAD_T, PAD_B = 35, 15, 10, 28
    T_MIN, T_MAX = 20, 100
    HIT_R = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pts: list[list[int]] = []
        self._idle_speed = 0.0
        self._drag = -1
        self._hover = -1
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_curve(self, temp_curve: list, speed_curve: list, idle_speed: float = 0.0) -> None:
        self._pts = [[int(t), int(s)] for t, s in zip(temp_curve, speed_curve)]
        self._idle_speed = float(idle_speed)
        self._drag = -1
        self._hover = -1
        self.update()

    def get_curve(self) -> tuple[list[int], list[int], float]:
        return [p[0] for p in self._pts], [p[1] for p in self._pts], self._idle_speed

    def set_idle_speed(self, val: float) -> None:
        self._idle_speed = float(val)
        self.update()

    def _px(self, temp: float, pct: float) -> QPointF:
        cw = self.width() - self.PAD_L - self.PAD_R
        ch = self.height() - self.PAD_T - self.PAD_B
        x = self.PAD_L + (temp - self.T_MIN) / (self.T_MAX - self.T_MIN) * cw
        y = self.PAD_T + ch - pct / 100.0 * ch
        return QPointF(x, y)

    def _from_px(self, px_x: float, px_y: float) -> tuple[float, float]:
        cw = self.width() - self.PAD_L - self.PAD_R
        ch = self.height() - self.PAD_T - self.PAD_B
        temp = self.T_MIN + (px_x - self.PAD_L) / cw * (self.T_MAX - self.T_MIN)
        pct = (self.PAD_T + ch - px_y) / ch * 100.0
        return temp, pct

    def _nearest(self, pos: QPointF) -> int:
        best, best_d = -1, float(self.HIT_R)
        for i, (t, s) in enumerate(self._pts):
            pt = self._px(t, s)
            d = ((pos.x() - pt.x()) ** 2 + (pos.y() - pt.y()) ** 2) ** 0.5
            if d < best_d:
                best_d, best = d, i
        return best

    def mousePressEvent(self, ev):
        pos = ev.position()
        if ev.button() == Qt.MouseButton.LeftButton:
            nearest = self._nearest(pos)
            if nearest >= 0:
                self._drag = nearest
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                self._add_point(pos)
        elif ev.button() == Qt.MouseButton.RightButton:
            self._remove_point(pos)

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        if self._drag >= 0:
            t, s = self._from_px(pos.x(), pos.y())
            i = self._drag
            t_lo = self._pts[i - 1][0] + 1 if i > 0 else self.T_MIN + 1
            t_hi = self._pts[i + 1][0] - 1 if i < len(self._pts) - 1 else self.T_MAX - 1
            self._pts[i][0] = int(round(max(t_lo, min(t_hi, t))))
            self._pts[i][1] = int(round(max(0.0, min(100.0, s))))
            self.update()
        else:
            h = self._nearest(pos)
            if h != self._hover:
                self._hover = h
                self.setCursor(
                    Qt.CursorShape.OpenHandCursor if h >= 0
                    else Qt.CursorShape.CrossCursor
                )

    def mouseReleaseEvent(self, ev):
        if self._drag >= 0:
            self._drag = -1
            self._hover = -1
            self.setCursor(Qt.CursorShape.CrossCursor)
            temps, speeds, _ = self.get_curve()
            self.curve_changed.emit(temps, speeds)

    def _add_point(self, pos: QPointF) -> None:
        t, s = self._from_px(pos.x(), pos.y())
        t = int(round(max(self.T_MIN + 1, min(self.T_MAX - 1, t))))
        s = int(round(max(0.0, min(100.0, s))))
        for existing_t, _ in self._pts:
            if abs(existing_t - t) < 2:
                return
        idx = sum(1 for pt in self._pts if pt[0] < t)
        self._pts.insert(idx, [t, s])
        self._drag = idx
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def _remove_point(self, pos: QPointF) -> None:
        if len(self._pts) <= 2:
            return
        nearest = self._nearest(pos)
        if nearest >= 0:
            self._pts.pop(nearest)
            self._hover = -1
            self.update()
            temps, speeds, _ = self.get_curve()
            self.curve_changed.emit(temps, speeds)

    def paintEvent(self, event):
        if not self._pts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cw = w - self.PAD_L - self.PAD_R
        ch = h - self.PAD_T - self.PAD_B

        # Grid
        p.setPen(QPen(QColor(36, 36, 42), 1))
        for t in (40, 60, 80):
            pt = self._px(t, 0)
            p.drawLine(QPointF(pt.x(), self.PAD_T), QPointF(pt.x(), self.PAD_T + ch))
        for pct in (25, 50, 75):
            pt = self._px(self.T_MIN, pct)
            p.drawLine(QPointF(self.PAD_L, pt.y()), QPointF(self.PAD_L + cw, pt.y()))

        # Axis labels
        p.setPen(QColor(70, 70, 80))
        p.setFont(QFont("Sans Serif", 7))
        for t in (40, 60, 80):
            pt = self._px(t, 0)
            p.drawText(QRectF(pt.x() - 14, self.PAD_T + ch + 4, 28, 16),
                       Qt.AlignmentFlag.AlignCenter, f"{t}°")
        for pct in (0, 50, 100):
            pt = self._px(self.T_MIN, pct)
            p.drawText(QRectF(0, pt.y() - 7, self.PAD_L - 4, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       str(pct))

        # Extended curve (idle flat + points + max extension)
        ext = ([(self.T_MIN, self._idle_speed)]
               + [(pt[0], pt[1]) for pt in self._pts]
               + [(self.T_MAX, self._pts[-1][1])])

        # Fill
        fill = QPainterPath()
        fill.moveTo(self._px(ext[0][0], 0))
        for t, s in ext:
            fill.lineTo(self._px(t, s))
        fill.lineTo(self._px(ext[-1][0], 0))
        fill.closeSubpath()
        p.fillPath(fill, theme.qcolor("accent", 28))

        # Curve line
        path = QPainterPath()
        path.moveTo(self._px(ext[0][0], ext[0][1]))
        for t, s in ext[1:]:
            path.lineTo(self._px(t, s))
        p.setPen(QPen(theme.qcolor("accent"), 1.8,
                      Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

        # Control points
        for i, (t, s) in enumerate(self._pts):
            pt = self._px(t, s)
            is_drag = i == self._drag
            is_hover = i == self._hover

            if is_drag:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor("accent", 55))
                p.drawEllipse(pt, 15, 15)

            p.setPen(QPen(QColor(20, 20, 32), 1.5))
            p.setBrush(QColor(140, 155, 255) if (is_drag or is_hover) else theme.qcolor("accent"))
            p.drawEllipse(pt, 7, 7)

            if is_drag:
                p.setPen(QColor(220, 220, 235))
                p.setFont(QFont("Sans Serif", 8, QFont.Weight.Bold))
                lbl = f"{t}°  {s}%"
                lx = pt.x() + 14
                ly = pt.y() - 16
                if lx + 62 > w:
                    lx = pt.x() - 74
                if ly < self.PAD_T:
                    ly = pt.y() + 10
                p.drawText(QRectF(lx, ly, 64, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)

        p.end()


class KeyboardPreview(QWidget):
    """Backlit OMEN 17 keyboard preview: full layout with numpad + under-key glow.

    Single physical RGB zone, so the whole board glows one colour. Light bleeds
    up through the gaps between keys (drawn via an additive radial glow under
    semi-opaque keycaps); legends are lit in the backlight colour.
    """

    # Positioned key map for a full-size OMEN 16/17 keyboard.
    # (label, x, y, w, h) in key-units. Main block spans x 0..15, numpad
    # 15.5..19.5. Supports tall keys (numpad '+', Enter) and the nested
    # inverted-T arrow cluster at the bottom-right of the main block.
    _COLS = 19.5
    _ROWS_N = 6
    _NP = 15.5  # numpad left edge
    _KEYS: list[tuple[str, float, float, float, float]] = [
        # row 0 — function row + top-right cluster (OMEN, menu, PrtSc, power)
        ("esc",0,0,1,1),("F1",1,0,1,1),("F2",2,0,1,1),("F3",3,0,1,1),
        ("F4",4,0,1,1),("F5",5,0,1,1),("F6",6,0,1,1),("F7",7,0,1,1),
        ("F8",8,0,1,1),("F9",9,0,1,1),("F10",10,0,1,1),("F11",11,0,1,1),
        ("F12",12,0,1,1),("ins",13,0,1,1),("del",14,0,1,1),
        ("◆",_NP,0,1,1),("▤",_NP+1,0,1,1),("prt",_NP+2,0,1,1),("⏻",_NP+3,0,1,1),
        # row 1 — number row + numpad top (NumLk / * -)
        ("`",0,1,1,1),("1",1,1,1,1),("2",2,1,1,1),("3",3,1,1,1),("4",4,1,1,1),
        ("5",5,1,1,1),("6",6,1,1,1),("7",7,1,1,1),("8",8,1,1,1),("9",9,1,1,1),
        ("0",10,1,1,1),("-",11,1,1,1),("=",12,1,1,1),("⌫",13,1,2,1),
        ("num",_NP,1,1,1),("/",_NP+1,1,1,1),("*",_NP+2,1,1,1),("-",_NP+3,1,1,1),
        # row 2 — qwerty + numpad 7 8 9 and tall '+'
        ("tab",0,2,1.5,1),("Q",1.5,2,1,1),("W",2.5,2,1,1),("E",3.5,2,1,1),
        ("R",4.5,2,1,1),("T",5.5,2,1,1),("Y",6.5,2,1,1),("U",7.5,2,1,1),
        ("I",8.5,2,1,1),("O",9.5,2,1,1),("P",10.5,2,1,1),("[",11.5,2,1,1),
        ("]",12.5,2,1,1),("\\",13.5,2,1.5,1),
        ("7",_NP,2,1,1),("8",_NP+1,2,1,1),("9",_NP+2,2,1,1),("+",_NP+3,2,1,2),
        # row 3 — home row + numpad 4 5 6
        ("caps",0,3,1.75,1),("A",1.75,3,1,1),("S",2.75,3,1,1),("D",3.75,3,1,1),
        ("F",4.75,3,1,1),("G",5.75,3,1,1),("H",6.75,3,1,1),("J",7.75,3,1,1),
        ("K",8.75,3,1,1),("L",9.75,3,1,1),(";",10.75,3,1,1),("'",11.75,3,1,1),
        ("↵",12.75,3,2.25,1),
        ("4",_NP,3,1,1),("5",_NP+1,3,1,1),("6",_NP+2,3,1,1),
        # row 4 — shift row + nested up-arrow + numpad 1 2 3 and tall Enter
        ("shift",0,4,1.75,1),("Z",1.75,4,1,1),("X",2.75,4,1,1),("C",3.75,4,1,1),
        ("V",4.75,4,1,1),("B",5.75,4,1,1),("N",6.75,4,1,1),("M",7.75,4,1,1),
        (",",8.75,4,1,1),(".",9.75,4,1,1),("/",10.75,4,1,1),("shift",11.75,4,2.75,1),
        ("1",_NP,4,1,1),("2",_NP+1,4,1,1),("3",_NP+2,4,1,1),("↵",_NP+3,4,1,2),
        # row 5 — bottom row + small inverted-T arrows (half-height) + numpad 0 .
        ("ctrl",0,5,1.25,1),("fn",1.25,5,1.25,1),("⊞",2.5,5,1.25,1),
        ("alt",3.75,5,1.25,1),("",5,5,4.5,1),("alt",9.5,5,1,1),("✦",10.5,5,1,1),
        ("◄",11.5,5.5,1,0.5),("▲",12.5,5,1,0.5),("▼",12.5,5.5,1,0.5),("►",13.5,5.5,1,0.5),
        ("0",_NP,5,2,1),(".",_NP+2,5,1,1),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(0, 200, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return max(96, int(width / 3.25))

    def sizeHint(self) -> QSize:
        return QSize(600, 185)

    def set_color(self, hex_color: str) -> None:
        self._color = QColor(f"#{hex_color}")
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad, gap = 9, 2.2
        cell_w = (w - pad * 2) / self._COLS
        cell_h = (h - pad * 2) / self._ROWS_N
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        dark = theme.is_dark()

        if dark:
            body_c, cap_c, cap_edge = QColor(13, 13, 18), QColor(20, 20, 27, 232), QColor(48, 48, 60, 200)
            hi_c = QColor(70, 70, 86, 90)
            glow_mode = edge_mode = QPainter.CompositionMode.CompositionMode_Plus
            glow_a, edge_a = (110, 55), 70
            legend = QColor(min(255, int(r * 0.45 + 160)),
                            min(255, int(g * 0.45 + 160)),
                            min(255, int(b * 0.45 + 160)))
        else:
            body_c, cap_c, cap_edge = QColor(202, 205, 213), QColor(235, 237, 241, 235), QColor(188, 192, 200, 230)
            hi_c = QColor(255, 255, 255, 150)
            glow_mode = edge_mode = QPainter.CompositionMode.CompositionMode_SourceOver
            glow_a, edge_a = (130, 70), 150
            legend = QColor(int(r * 0.6), int(g * 0.6), int(b * 0.6))

        body = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(body_c)
        p.drawRoundedRect(body, 9, 9)

        # Backlight glow under the keys (additive in dark, tint in light)
        area = QRectF(pad, pad, w - pad * 2, h - pad * 2)
        p.setCompositionMode(glow_mode)
        cx, cy = area.center().x(), area.center().y()
        rad = max(area.width(), area.height()) * 0.62
        grad = QRadialGradient(cx, cy, rad)
        grad.setColorAt(0.0, QColor(r, g, b, glow_a[0]))
        grad.setColorAt(0.55, QColor(r, g, b, glow_a[1]))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setBrush(grad)
        p.drawRoundedRect(area, 6, 6)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        for label, x, y, wu, hu in self._KEYS:
            rect = QRectF(
                pad + x * cell_w + gap / 2,
                pad + y * cell_h + gap / 2,
                wu * cell_w - gap,
                hu * cell_h - gap,
            )
            # Semi-opaque keycap — lets a little glow seep around it
            p.setPen(QPen(cap_edge, 0.8))
            p.setBrush(cap_c)
            p.drawRoundedRect(rect, 3, 3)
            # Top highlight for a moulded keycap feel
            p.setPen(QPen(hi_c, 1))
            p.drawLine(rect.topLeft() + QPointF(3, 1.2),
                       rect.topRight() + QPointF(-3, 1.2))
            # Emissive bottom edge — light leaking from under the key
            p.setCompositionMode(edge_mode)
            p.setPen(QPen(QColor(r, g, b, edge_a), 1.4))
            p.drawLine(rect.bottomLeft() + QPointF(2, -0.6),
                       rect.bottomRight() + QPointF(-2, -0.6))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            # Lit legend
            if label.strip():
                p.setPen(legend)
                sz = 5 if len(label) > 2 else 6
                p.setFont(QFont("Sans Serif", sz))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class ColorSwatch(QPushButton):
    """Round color button for RGB presets."""

    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: #{hex_color};
                border: 2px solid #404040;
                border-radius: 17px;
            }}
            QPushButton:hover {{ border-color: #ffffff; }}
        """)

    @property
    def hex_color(self) -> str:
        return self._hex


# ── Color Picker Dialog ───────────────────────────────────────────────────────

class _SatValSquare(QWidget):
    """Saturation × Value gradient picker for a fixed hue."""
    changed = pyqtSignal(int, int)  # sat, val  (0-255)

    def __init__(self, hue: int, sat: int, val: int,
                 w: int = 222, h: int = 160, parent=None):
        super().__init__(parent)
        self._hue, self._sat, self._val = hue, sat, val
        self.setFixedSize(w, h)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_hue(self, hue: int) -> None:
        self._hue = hue
        self.update()

    def set_sv(self, sat: int, val: int) -> None:
        self._sat, self._val = sat, val
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        g1 = QLinearGradient(0, 0, w, 0)
        g1.setColorAt(0, QColor(255, 255, 255))
        g1.setColorAt(1, QColor.fromHsv(self._hue, 255, 255))
        p.fillRect(0, 0, w, h, g1)
        g2 = QLinearGradient(0, 0, 0, h)
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(0, 0, w, h, g2)
        cx = int(self._sat / 255 * w)
        cy = int((1 - self._val / 255) * h)
        p.setPen(QPen(QColor(0, 0, 0, 120), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.drawEllipse(QPointF(cx, cy), 6, 6)
        p.end()

    def mousePressEvent(self, ev):   self._pick(ev.position())
    def mouseMoveEvent(self, ev):    self._pick(ev.position())

    def _pick(self, pos) -> None:
        w, h = self.width(), self.height()
        x = max(0.0, min(pos.x(), w - 1))
        y = max(0.0, min(pos.y(), h - 1))
        self._sat = int(x / w * 255)
        self._val = int((1 - y / h) * 255)
        self.changed.emit(self._sat, self._val)
        self.update()


class _HueSlider(QWidget):
    """Horizontal rainbow hue slider."""
    changed = pyqtSignal(int)  # hue 0-359

    def __init__(self, hue: int, parent=None):
        super().__init__(parent)
        self._hue = hue
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_hue(self, hue: int) -> None:
        self._hue = hue
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsv(int(i * 60), 255, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)
        cx = int(self._hue / 359 * w)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawRoundedRect(QRectF(cx - 3, 1, 6, h - 2), 2, 2)
        p.end()

    def mousePressEvent(self, ev):   self._pick(ev.position())
    def mouseMoveEvent(self, ev):    self._pick(ev.position())

    def _pick(self, pos) -> None:
        x = max(0.0, min(pos.x(), self.width() - 1))
        self._hue = int(x / self.width() * 359)
        self.changed.emit(self._hue)
        self.update()


class InlineColorPicker(QWidget):
    """Embeddable color picker: S×V square + hue slider + hex input. No dialog."""

    color_changed = pyqtSignal(str)  # 6-char hex, no #

    def __init__(self, initial_hex: str = "ff0000", parent=None):
        super().__init__(parent)
        c = QColor(f"#{initial_hex}")
        h, s, v, _ = c.getHsv()
        self._hue = max(0, h)
        self._sat, self._val = s, v
        self._build()

    def _build(self):
        from PyQt6.QtWidgets import QLineEdit
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._sq = _SatValSquare(self._hue, self._sat, self._val, w=200, h=140)
        self._sq.changed.connect(self._on_sv)
        root.addWidget(self._sq)

        self._hue_sl = _HueSlider(self._hue)
        self._hue_sl.changed.connect(self._on_hue)
        root.addWidget(self._hue_sl)

        hl = QHBoxLayout()
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self._hex_in = QLineEdit()
        self._hex_in.setMaxLength(7)
        self._hex_in.setFixedHeight(24)
        self._hex_in.setStyleSheet(
            "QLineEdit{background:#2a2a2e;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:2px 6px;font-family:monospace;font-size:11px;}"
            "QLineEdit:focus{border-color:#5566ff;}"
        )
        self._hex_in.textEdited.connect(self._on_hex)
        hl.addWidget(self._hex_in)
        hl.addStretch()
        root.addLayout(hl)

        self._refresh_display()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_color(self, hex_color: str) -> None:
        c = QColor(f"#{hex_color}")
        h, s, v, _ = c.getHsv()
        self._hue = max(0, h)
        self._sat, self._val = s, v
        self._sq.set_hue(self._hue)
        self._sq.set_sv(s, v)
        self._hue_sl.set_hue(self._hue)
        self._refresh_display()

    def current_hex(self) -> str:
        return QColor.fromHsv(self._hue, self._sat, self._val).name()[1:]

    # ── Internal ─────────────────────────────────────────────────────────────

    def _refresh_display(self) -> None:
        self._hex_in.setText(f"#{self.current_hex()}")

    def _on_hue(self, hue: int) -> None:
        self._hue = hue
        self._sq.set_hue(hue)
        self._refresh_display()
        self.color_changed.emit(self.current_hex())

    def _on_sv(self, sat: int, val: int) -> None:
        self._sat, self._val = sat, val
        self._refresh_display()
        self.color_changed.emit(self.current_hex())

    def _on_hex(self, text: str) -> None:
        t = text.strip().lstrip("#")
        if len(t) == 6:
            c = QColor(f"#{t}")
            if c.isValid():
                h, s, v, _ = c.getHsv()
                self._hue, self._sat, self._val = max(0, h), s, v
                self._sq.set_hue(self._hue)
                self._sq.set_sv(s, v)
                self._hue_sl.set_hue(self._hue)
                self.color_changed.emit(t)


class ColorPickerDialog(QDialog):
    """Compact dark-themed color picker replacing QColorDialog."""

    def __init__(self, initial_hex: str = "ff0000", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pick Color")
        self.setModal(True)
        self.setFixedSize(250, 285)
        self.setStyleSheet("QDialog { background: #18181c; }")

        c = QColor(f"#{initial_hex}")
        h, s, v, _ = c.getHsv()
        self._hue = max(0, h)
        self._sat, self._val = s, v
        self._initial = initial_hex
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(14, 14, 14, 14)

        self._sq = _SatValSquare(self._hue, self._sat, self._val)
        self._sq.changed.connect(self._on_sv)
        root.addWidget(self._sq)

        self._hue_sl = _HueSlider(self._hue)
        self._hue_sl.changed.connect(self._on_hue)
        root.addWidget(self._hue_sl)

        hl = QHBoxLayout()
        hl.setSpacing(8)

        self._old_sw = QLabel()
        self._old_sw.setFixedSize(26, 26)
        self._old_sw.setStyleSheet(
            f"background:#{self._initial};border-radius:4px;border:1px solid #333;"
        )
        hl.addWidget(self._old_sw)

        self._new_sw = QLabel()
        self._new_sw.setFixedSize(26, 26)
        hl.addWidget(self._new_sw)

        self._hex_in = QLineEdit()
        self._hex_in.setFixedHeight(26)
        self._hex_in.setMaxLength(7)
        self._hex_in.setStyleSheet(
            "QLineEdit{background:#2a2a2e;color:#ccc;border:1px solid #444;"
            "border-radius:4px;padding:2px 6px;font-family:monospace;font-size:12px;}"
            "QLineEdit:focus{border-color:#5566ff;}"
        )
        self._hex_in.textEdited.connect(self._on_hex)
        hl.addWidget(self._hex_in)
        root.addLayout(hl)

        bl = QHBoxLayout()
        bl.addStretch()
        _c = QPushButton("Cancel")
        _c.setStyleSheet(
            "QPushButton{background:#2a2a2e;color:#aaa;border:1px solid #444;"
            "border-radius:6px;padding:5px 16px;font-size:12px;}"
            "QPushButton:hover{border-color:#888;color:#ddd;}"
        )
        _c.clicked.connect(self.reject)
        bl.addWidget(_c)
        _ok = QPushButton("OK")
        _ok.setStyleSheet(
            "QPushButton{background:#5566ff;color:#fff;border:none;"
            "border-radius:6px;padding:5px 16px;font-size:12px;}"
            "QPushButton:hover{background:#6677ff;}"
        )
        _ok.clicked.connect(self.accept)
        bl.addWidget(_ok)
        root.addLayout(bl)

        self._refresh()

    def _current_hex(self) -> str:
        return QColor.fromHsv(self._hue, self._sat, self._val).name()[1:]

    def _refresh(self):
        hex_c = self._current_hex()
        self._new_sw.setStyleSheet(
            f"background:#{hex_c};border-radius:4px;border:1px solid #333;"
        )
        self._hex_in.setText(f"#{hex_c}")

    def _on_hue(self, hue: int):
        self._hue = hue
        self._sq.set_hue(hue)
        self._refresh()

    def _on_sv(self, sat: int, val: int):
        self._sat, self._val = sat, val
        self._refresh()

    def _on_hex(self, text: str):
        t = text.strip().lstrip("#")
        if len(t) == 6:
            c = QColor(f"#{t}")
            if c.isValid():
                h, s, v, _ = c.getHsv()
                self._hue, self._sat, self._val = max(0, h), s, v
                self._sq.set_hue(self._hue)
                self._sq.set_sv(s, v)
                self._hue_sl.set_hue(self._hue)
                self._new_sw.setStyleSheet(
                    f"background:#{t};border-radius:4px;border:1px solid #333;"
                )

    def selected_hex(self) -> str:
        """Returns selected color as 6-char lowercase hex without #."""
        return self._current_hex()
