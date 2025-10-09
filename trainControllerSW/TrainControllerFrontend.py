"""
Train Controller Frontend
"""
from __future__ import annotations

try:
    from .TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph
except Exception:
    from TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph


class TrainControllerFrontend:
    def __init__(self, train_id: str = "T1") -> None:
        self.ctrl = TrainControllerBackend(train_id=train_id)
        # demo-only internal speed if no train model is hooked up
        self._demo_speed_mps = 0.0

    # ---------- UI -> Backend setters ----------
    def set_auto_mode(self, enabled: bool) -> None:
        self.ctrl.set_auto_mode(enabled)

    def set_driver_speed_mph(self, mph: float) -> None:
        self.ctrl.set_driver_speed(mph_to_mps(mph))

    def set_ctc_command(self, speed_mph: float, authority_m: float) -> None:
        self.ctrl.set_commanded_speed(mph_to_mps(speed_mph))
        self.ctrl.set_commanded_authority(authority_m)

    def set_speed_limit_mph(self, mph: float) -> None:
        self.ctrl.set_speed_limit(mph_to_mps(mph))

    def set_kp(self, kp: float) -> None:
        self.ctrl.set_kp(kp)

    def set_ki(self, ki: float) -> None:
        self.ctrl.set_ki(ki)

    def set_service_brake(self, active: bool) -> None:
        self.ctrl.set_service_brake(active)

    def set_emergency_brake(self, active: bool) -> None:
        self.ctrl.set_emergency_brake(active)

    def set_doors_left(self, open_: bool) -> None:
        self.ctrl.set_doors_left(open_)

    def set_doors_right(self, open_: bool) -> None:
        self.ctrl.set_doors_right(open_)

    def set_headlights(self, on: bool) -> None:
        self.ctrl.set_headlights(on)

    def set_cabin_lights(self, on: bool) -> None:
        self.ctrl.set_cabin_lights(on)

    def set_temp_c(self, temp_c: float) -> None:
        self.ctrl.set_temp_setpoint_c(temp_c)

    def set_actual_speed_mph(self, mph: float) -> None:
        self._demo_speed_mps = mph_to_mps(mph)
        self.ctrl.set_actual_speed(self._demo_speed_mps)

    # ---------- Tick & telemetry ----------
    def tick(self, dt_s: float) -> dict:
        """
        Demo physics:
          - If emergency brake: strong decel
          - Else if service brake: medium decel
          - Else: accelerate a bit if there is power, coast otherwise
        """
        # 1) Run backend with the current measured speed
        self.ctrl.set_actual_speed(self._demo_speed_mps)
        self.ctrl.update(dt_s)

        # 2) Demo speed update (ONLY for sandbox)
        disp = self.ctrl.get_display_values()
        power_kw = float(disp.get("power_kw", 0.0))
        eb_on = bool(disp.get("emergency_brake", False))
        sb_on = bool(disp.get("service_brake", False))

        if eb_on:
            a = -3.0  # m/s^2
        elif sb_on:
            a = -1.0
        else:
            # Crude mapping power->accel for demo
            a = 0.02 * power_kw  # cap happens in backend already

        self._demo_speed_mps = max(0.0, self._demo_speed_mps + a * dt_s)
        self.ctrl.set_actual_speed(self._demo_speed_mps)

        # 3) Return telemetry for the UI
        return self.ctrl.get_display_values()
