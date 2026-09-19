"""Closed-loop control of the player: read the overlay, correct, repeat.

Everything here exists because open-loop input does not work. Minecraft
movement is continuous, creative flight glides after the key is released, and
mouse sensitivity is a per-user setting -- so "fly right for 90ms" accumulates
error until the mural is being built in the wrong column. Each primitive below
reads the real position back out of the F3 overlay and corrects.

One consequence worth knowing: position tolerance is deliberately loose
(~0.25 blocks). Aim is recomputed from the *measured* eye position rather than
the intended one, so residual position error is cancelled by the aim step. All
the position controller has to guarantee is that the target stays within reach
and below eye level -- not that the player is exactly where the plan said.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from .input import Controls
from .plan import aim_angles
from .vision import F3ReadError, FontModel, PlayerState, ScreenCapture, parse, yaw_delta

log = logging.getLogger(__name__)

# Yaw the player holds while flying, so that WASD maps to fixed world axes.
MOVE_YAW = 180.0  # facing north (-Z), i.e. at the wall

# Key per (axis, direction) while facing north.
AXIS_KEYS = {
    ("x", +1): "d",
    ("x", -1): "a",
    ("y", +1): "space",
    ("y", -1): "lshift",
    ("z", +1): "s",
    ("z", -1): "w",
}


class Aborted(RuntimeError):
    """The abort hotkey was pressed."""


@dataclass
class Tuning:
    position_tolerance: float = 0.25
    coarse_band: float = 1.0
    aim_tolerance: float = 0.4  # degrees
    poll_interval: float = 0.03
    move_timeout: float = 20.0
    fly_speed: float = 10.9  # blocks/sec, default creative flight
    max_counts_per_step: int = 400


class AbortWatcher:
    """Background watch for the panic hotkey (F12 by default).

    The builder holds movement keys down for seconds at a time, so there has to
    be a way to stop it that does not involve alt-tabbing to the terminal --
    alt-tab itself leaves the held keys stuck down.
    """

    def __init__(self, vk: int = 0x7B):  # VK_F12
        self.vk = vk
        self._fired = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import ctypes

            user32 = ctypes.WinDLL("user32")
        except (ImportError, OSError):
            log.warning("abort hotkey unavailable off Windows; use Ctrl-C")
            return

        def loop() -> None:
            while not self._stop.is_set():
                if user32.GetAsyncKeyState(self.vk) & 0x8000:
                    self._fired.set()
                    return
                time.sleep(0.02)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def fired(self) -> bool:
        return self._fired.is_set()


class Controller:
    def __init__(
        self,
        capture: ScreenCapture,
        font: FontModel,
        controls: Controls,
        deg_per_count_x: float,
        deg_per_count_y: float,
        tuning: Tuning | None = None,
        abort: AbortWatcher | None = None,
    ):
        self.capture = capture
        self.font = font
        self.controls = controls
        self.dpc_x = deg_per_count_x
        self.dpc_y = deg_per_count_y
        self.t = tuning or Tuning()
        self.abort = abort

    # --- sensing ------------------------------------------------------------

    def read_state(self, retries: int = 6) -> PlayerState:
        """Read the overlay, retrying through transient misreads.

        A frame can be unreadable because the capture landed mid-redraw or a
        chat message overlapped the text. Retrying is cheap; guessing is not.
        """
        last: Exception | None = None
        for _ in range(retries):
            self._check_abort()
            try:
                return parse(self.font.read_all(self.capture.grab()))
            except F3ReadError as exc:
                last = exc
                time.sleep(0.04)
        raise F3ReadError(f"could not read the F3 overlay after {retries} tries: {last}")

    def _check_abort(self) -> None:
        if self.abort is not None and self.abort.fired:
            self.controls.release_all()
            raise Aborted("abort hotkey pressed")

    # --- aiming -------------------------------------------------------------

    def aim(self, target_yaw: float, target_pitch: float, max_steps: int = 25) -> PlayerState:
        state = self.read_state()
        for _ in range(max_steps):
            dyaw = yaw_delta(state.yaw, target_yaw)
            dpitch = target_pitch - state.pitch
            if abs(dyaw) <= self.t.aim_tolerance and abs(dpitch) <= self.t.aim_tolerance:
                return state
            cx = self._clamp_counts(dyaw / self.dpc_x)
            cy = self._clamp_counts(dpitch / self.dpc_y)
            self.controls.move(cx, cy)
            time.sleep(0.05)
            state = self.read_state()
        log.warning(
            "aim did not converge: yaw %.2f (want %.2f), pitch %.2f (want %.2f)",
            state.yaw, target_yaw, state.pitch, target_pitch,
        )
        return state

    def _clamp_counts(self, counts: float) -> int:
        limit = self.t.max_counts_per_step
        return int(max(-limit, min(limit, round(counts))))

    def aim_at(self, target: tuple[float, float, float]) -> PlayerState:
        """Aim at a world point, recomputing from the measured eye position."""
        state = self.read_state()
        yaw, pitch = aim_angles(state.eye, target)
        return self.aim(yaw, pitch)

    def face_move_direction(self) -> None:
        self.aim(MOVE_YAW, 0.0)

    # --- movement -----------------------------------------------------------

    def goto(self, x: float, y: float, z: float) -> PlayerState:
        """Fly to a position, holding yaw fixed so WASD maps to world axes."""
        self.face_move_direction()
        deadline = time.monotonic() + self.t.move_timeout
        state = self.read_state()

        # Coarse phase: hold keys down, dropping each axis as it closes in.
        while time.monotonic() < deadline:
            self._check_abort()
            errs = {"x": x - state.x, "y": y - state.y, "z": z - state.z}
            if all(abs(e) <= self.t.coarse_band for e in errs.values()):
                break
            for axis, err in errs.items():
                pos_key = AXIS_KEYS[(axis, +1)]
                neg_key = AXIS_KEYS[(axis, -1)]
                if abs(err) > self.t.coarse_band:
                    self.controls.hold(pos_key if err > 0 else neg_key)
                    self.controls.release(neg_key if err > 0 else pos_key)
                else:
                    self.controls.release(pos_key)
                    self.controls.release(neg_key)
            time.sleep(self.t.poll_interval)
            state = self.read_state()
        self.controls.release_all()

        # Fine phase: short taps sized from the remaining error, re-measuring
        # between each one so flight glide gets absorbed rather than modelled.
        while time.monotonic() < deadline:
            self._check_abort()
            state = self.read_state()
            errs = {"x": x - state.x, "y": y - state.y, "z": z - state.z}
            worst = max(errs, key=lambda a: abs(errs[a]))
            if abs(errs[worst]) <= self.t.position_tolerance:
                return state
            err = errs[worst]
            key = AXIS_KEYS[(worst, +1 if err > 0 else -1)]
            duration = max(0.02, min(0.20, abs(err) / self.t.fly_speed))
            self.controls.tap(key, duration)
            time.sleep(0.10)  # let the glide settle before re-measuring

        self.controls.release_all()
        raise TimeoutError(
            f"could not reach ({x:.2f}, {y:.2f}, {z:.2f}) within "
            f"{self.t.move_timeout}s; last position "
            f"({state.x:.2f}, {state.y:.2f}, {state.z:.2f})"
        )

    # --- placing ------------------------------------------------------------

    def place(self, target: tuple[float, float, float], slot: int) -> None:
        self.controls.select_hotbar(slot)
        self.aim_at(target)
        self.controls.click("right")
        time.sleep(0.04)


def calibrate_mouse(
    capture: ScreenCapture,
    font: FontModel,
    controls: Controls,
    counts: int = 200,
    samples: int = 3,
) -> tuple[float, float]:
    """Measure degrees of camera rotation per unit of mouse delta.

    Returns signed (x, y) ratios, so a sign convention that differs from the
    expected one is absorbed rather than producing a controller that turns the
    wrong way. Requires Windows "Enhance pointer precision" to be off -- with
    acceleration on, the ratio is not a constant and this measurement is
    meaningless.
    """
    controller = Controller(capture, font, controls, 1.0, 1.0)

    def measure(dx: int, dy: int) -> tuple[float, float]:
        before = controller.read_state()
        controls.move(dx, dy)
        time.sleep(0.15)
        after = controller.read_state()
        return yaw_delta(before.yaw, after.yaw), after.pitch - before.pitch

    # Level the camera first: pitch saturates at +-90, which would silently
    # truncate the vertical measurement.
    controller.aim(controller.read_state().yaw, 0.0)

    xs, ys = [], []
    for _ in range(samples):
        dyaw, _ = measure(counts, 0)
        xs.append(dyaw / counts)
        _, dpitch = measure(0, counts)
        ys.append(dpitch / counts)
        controls.move(0, -counts)  # undo, keeping pitch near the horizon
        time.sleep(0.12)

    dpc_x = sum(xs) / len(xs)
    dpc_y = sum(ys) / len(ys)
    if abs(dpc_x) < 1e-6 or abs(dpc_y) < 1e-6:
        raise RuntimeError(
            "calibration measured no camera movement. Check that Minecraft has "
            "focus, that the cursor is grabbed (not in a menu), and that raw "
            "input is enabled."
        )
    return dpc_x, dpc_y
