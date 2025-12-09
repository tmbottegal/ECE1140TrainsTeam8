import sys
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from trainModel.train_model_backend import TrainModelBackend


@pytest.fixture
def backend():
    tm = TrainModelBackend(line_name="Green Line")
    tm.train_id = "T4"
    return tm


def step_for_time(tm: TrainModelBackend, total_time_s: float, dt: float = 0.1):
    remaining = total_time_s
    while remaining > 1e-6:
        sub = min(dt, remaining)
        tm._step_dt(sub)
        remaining -= sub


def test_report_state_contains_ids(backend):
    state = backend.report_state()
    assert state["line_name"] == "Green Line"
    assert state["train_id"] == "T4"


def test_acceleration_on_level_track(backend):
    backend.velocity = 0.0
    backend.grade_percent = 0.0
    backend.power_kw = 200.0
    backend.service_brake = False
    backend.emergency_brake = False

    step_for_time(backend, total_time_s=5.0, dt=0.1)
    assert backend.velocity > 0.0
    assert backend.position > 0.0

    assert backend.acceleration <= backend.MAX_ACCEL + 1e-3


def test_service_brake_deceleration(backend):
    backend.velocity = 15.0  # m/s
    backend.power_kw = 0.0
    backend.grade_percent = 0.0
    backend.service_brake = True
    backend.emergency_brake = False

    v0 = backend.velocity
    step_for_time(backend, total_time_s=5.0, dt=0.1)

    assert 0.0 <= backend.velocity < v0

    assert backend.acceleration < 0.0
    assert backend.acceleration == pytest.approx(backend.MAX_DECEL, rel=0.2)



def test_emergency_brake_deceleration(backend):
    backend.velocity = 15.0
    backend.power_kw = 0.0
    backend.grade_percent = 0.0
    backend.service_brake = False
    backend.emergency_brake = True

    v0 = backend.velocity
    step_for_time(backend, total_time_s=3.0, dt=0.1)

    assert 0.0 <= backend.velocity < v0

    assert backend.acceleration <= backend.MAX_EBRAKE + 1e-3


def test_authority_limited_braking(backend):
    backend.velocity = 15.0
    backend.power_kw = 0.0
    backend.grade_percent = 0.0
    backend.service_brake = False
    backend.emergency_brake = False

    service_a = abs(backend.MAX_DECEL)
    stopping_distance = backend.velocity ** 2 / (2.0 * service_a)
    backend.authority_m = stopping_distance * 0.8

    step_for_time(backend, total_time_s=3.0, dt=0.1)

    assert backend.velocity < 15.0
    assert backend.authority_m >= 0.0


def test_block_occupancy_flag(backend):
    backend.velocity = 10.0
    backend.block_occupied = False

    step_for_time(backend, total_time_s=1.0, dt=0.1)
    assert backend.block_occupied is True

    backend.velocity = 0.0
    backend._step_dt(0.1)
    assert backend.block_occupied is False


def test_board_passengers_respects_capacity(backend):
    backend.passenger_count = 270
    backend.CAPACITY = 272

    boarded = backend.board_passengers(10)

    assert boarded == 2
    assert backend.passenger_count == 272  # at capacity, not beyond


def test_alight_passengers_respects_available(backend):
    backend.passenger_count = 50

    exited = backend.alight_passengers(80)
    assert exited == 50
    assert backend.passenger_count == 0


def test_temperature_control_heating(backend):
    backend.actual_temperature = 18.0
    backend.temperature_setpoint = 22.0
    backend.heating = True
    backend.air_conditioning = False

    step_for_time(backend, total_time_s=300.0, dt=1.0)
    assert backend.actual_temperature > 18.0
    assert backend.actual_temperature <= backend.temperature_setpoint + 0.5


def test_temperature_control_cooling(backend):
    backend.actual_temperature = 26.0
    backend.temperature_setpoint = 22.0
    backend.heating = False
    backend.air_conditioning = True

    step_for_time(backend, total_time_s=300.0, dt=1.0)

    assert backend.actual_temperature < 26.0
    assert backend.actual_temperature >= backend.temperature_setpoint - 0.5


def test_failure_flags_trigger_emergency_brake(backend):
    backend.velocity = 10.0
    backend.power_kw = 100.0
    backend.service_brake = False
    backend.emergency_brake = False

    backend.set_failure_state("engine", True)

    assert backend.engine_failure is True
    assert backend.emergency_brake is True

    v0 = backend.velocity
    step_for_time(backend, total_time_s=3.0, dt=0.1)

    assert backend.velocity <= v0
    assert backend.velocity >= 0.0

def test_cabin_lights_toggle(backend):
    # Initially False by default
    assert backend.cabin_lights is False

    backend.set_inputs(cabin_lights=True)
    assert backend.cabin_lights is True
    state = backend.report_state()
    assert state["cabin_lights"] is True

    backend.set_inputs(cabin_lights=False)
    assert backend.cabin_lights is False
    state = backend.report_state()
    assert state["cabin_lights"] is False

def test_headlights_toggle(backend):
    assert backend.headlights is False

    backend.set_inputs(headlights=True)
    assert backend.headlights is True
    assert backend.report_state()["headlights"] is True

    backend.set_inputs(headlights=False)
    assert backend.headlights is False
    assert backend.report_state()["headlights"] is False
