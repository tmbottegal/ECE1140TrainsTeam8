from __future__ import annotations
""" 
Train Controller Backend - CLEANED VERSION (No Grade/Beacon)

This module implements the core Train Controller logic according to the Use Case Model.

INPUTS (from Train Model via Frontend):
- commanded_speed_mps: Speed command from CTC/Track Circuit (m/s)
- commanded_authority_m: Authority distance from CTC/Track Circuit (meters)
- actual_speed_mps: Current train velocity from tachometer (m/s)

OUTPUTS (to Train Model):
- power_kw: Power command to train motor (kW)
- service_brake_out: Service brake activation flag (bool)
- emergency_brake_out: Emergency brake activation flag (bool)

DRIVER INPUTS (from Driver via UI):
- auto_mode: Auto/Manual mode selection (bool)
- driver_set_speed_mps: Manual speed setpoint (m/s)
- service_brake_cmd: Manual service brake command (bool)
- emergency_brake_cmd: Manual emergency brake command (bool)
- doors_left_open, doors_right_open: Door control (bool)
- headlights_on, cabin_lights_on: Light control (bool)
- temp_setpoint_c: Cabin temperature setpoint (°C)

ENGINEER INPUTS (from Engineer via UI):
- kp, ki: PI controller gains (float)
- speed_limit_mps: Line speed limit (m/s)

NOTE: Grade and beacon data are NOT part of Train Controller.
They flow directly: Track Model → Train Model (for physics simulation).
"""

from dataclasses import dataclass

# Conversion utilities
def mph_to_mps(v_mph: float) -> float: 
    """Convert miles per hour to meters per second"""
    return v_mph * 0.44704

def mps_to_mph(v_mps: float) -> float: 
    """Convert meters per second to miles per hour"""
    return v_mps / 0.44704

@dataclass
class TrainState:
    """
    Complete state of the Train Controller
    
    This dataclass holds all inputs, outputs, and internal state variables
    for the Train Controller module.
    """
    train_id: str = "T1"
    
    # PI Controller Gains (Engineer configurable)
    kp: float = 0.8  # Proportional gain
    ki: float = 0.3  # Integral gain
    
    # Speed Limits (Safety constraints)
    MAX_SPEED_MPS: float = mph_to_mps(70.0)  # Absolute maximum speed
    speed_limit_mps: float = mph_to_mps(70.0)  # Line speed limit from track
    
    # === INPUTS FROM TRAIN MODEL (via Track Circuit/CTC) ===
    commanded_speed_mps: float = 0.0     # Speed command from CTC
    commanded_authority_m: float = 0.0   # Authority from CTC (distance allowed to travel)
    actual_speed_mps: float = 0.0        # Actual velocity from train tachometer
    
    # === DRIVER INPUTS ===
    auto_mode: bool = True               # True=Auto (follow CTC), False=Manual (follow driver)
    driver_set_speed_mps: float = 0.0    # Driver's manual speed setpoint
    service_brake_cmd: bool = False      # Driver service brake command
    emergency_brake_cmd: bool = False    # Driver emergency brake command
    
    # === DRIVER CONTROLS (passed through to Train Model) ===
    doors_left_open: bool = False        # Left door control
    doors_right_open: bool = False       # Right door control
    headlights_on: bool = False          # Headlight control
    cabin_lights_on: bool = False        # Cabin light control
    temp_setpoint_c: float = 20.0        # Cabin temperature setpoint (°C)
    
    # === OUTPUTS TO TRAIN MODEL ===
    power_kw: float = 0.0                # Power command to motor (kW)
    service_brake_out: bool = False      # Service brake activation
    emergency_brake_out: bool = False    # Emergency brake activation
    
    # === INTERNAL STATE ===
    _i_err: float = 0.0  # Integral error accumulator for PI controller

class TrainControllerBackend:
    """
    Train Controller Backend - Core Control Logic
    
    This class implements the main train controller functionality:
    - PI speed control (Auto mode)
    - Manual speed control (Manual mode)
    - Safety enforcement (authority, speed limits, brakes)
    - Pass-through controls (doors, lights, temperature)
    
    Use Cases Implemented:
    - UC 4.0: Regulate train speed at velocity setpoint from CTC & Train Driver
    - UC 4.1: Set internal temperature setpoint
    - UC 4.2: Emergency Brake Activation by Driver
    - UC 4.3: Service Brake by Driver
    - UC 4.4: Engineer sets Kp & Ki
    - UC 4.5: Driver increase & decrease speed
    - UC 4.6: Use Speed & Authority from Track Circuit
    - UC 4.7: Train lights on and off
    - UC 4.8: Train doors open and close
    """
    
    def __init__(self, train_id: str = "T1") -> None:
        """Initialize the Train Controller with a unique train ID"""
        self.state = TrainState(train_id=train_id)
    
    # ======================================================================
    # SETTERS - INPUTS FROM TRAIN MODEL (received via Frontend)
    # ======================================================================
    
    def set_commanded_speed(self, speed_mps: float) -> None:
        """
        Set commanded speed from CTC/Track Circuit
        
        This is the target speed sent by the CTC office via the Track Circuit.
        In Auto mode, the controller will regulate to this speed.
        
        Args:
            speed_mps: Commanded speed in meters per second
        """
        self.state.commanded_speed_mps = max(0.0, float(speed_mps))
    
    def set_commanded_authority(self, authority_m: float) -> None:
        """
        Set commanded authority from CTC/Track Circuit
        
        Authority is the distance (in meters) the train is allowed to travel.
        If authority reaches 0, the controller will apply service brake.
        
        Args:
            authority_m: Authority distance in meters
        """
        self.state.commanded_authority_m = max(0.0, float(authority_m))
    
    def set_actual_speed(self, speed_mps: float) -> None:
        """
        Set actual speed from Train Model tachometer
        
        This is the real measured velocity of the train, used for feedback control.
        
        Args:
            speed_mps: Actual velocity in meters per second
        """
        self.state.actual_speed_mps = max(0.0, float(speed_mps))
    
    # ======================================================================
    # SETTERS - DRIVER INPUTS (from UI)
    # ======================================================================
    
    def set_auto_mode(self, enabled: bool) -> None:
        """
        Set controller mode (Auto/Manual)
        
        Auto mode: Follow commanded speed from CTC
        Manual mode: Follow driver's manual speed setpoint
        
        Args:
            enabled: True for Auto mode, False for Manual mode
        """
        self.state.auto_mode = bool(enabled)
    
    def set_driver_speed(self, speed_mps: float) -> None:
        """
        Set driver's manual speed setpoint (used in Manual mode)
        
        Args:
            speed_mps: Driver's desired speed in meters per second
        """
        self.state.driver_set_speed_mps = max(0.0, float(speed_mps))
    
    def set_service_brake(self, active: bool) -> None:
        """
        Set driver's service brake command
        
        When activated, overrides speed control and applies service brake.
        
        Args:
            active: True to activate service brake
        """
        self.state.service_brake_cmd = bool(active)
    
    def set_emergency_brake(self, active: bool) -> None:
        """
        Set driver's emergency brake command
        
        When activated, immediately stops all motion and overrides all other commands.
        
        Args:
            active: True to activate emergency brake
        """
        self.state.emergency_brake_cmd = bool(active)
    
    # ======================================================================
    # SETTERS - ENGINEER INPUTS (from UI)
    # ======================================================================
    
    def set_speed_limit(self, limit_mps: float) -> None:
        """
        Set line speed limit
        
        Controller will never command speed above this limit.
        
        Args:
            limit_mps: Speed limit in meters per second
        """
        self.state.speed_limit_mps = max(0.0, float(limit_mps))
    
    def set_kp(self, kp: float) -> None:
        """
        Set proportional gain for PI controller
        
        Args:
            kp: Proportional gain (typically 0.0 - 10.0)
        """
        self.state.kp = max(0.0, float(kp))
    
    def set_ki(self, ki: float) -> None:
        """
        Set integral gain for PI controller
        
        Args:
            ki: Integral gain (typically 0.0 - 10.0)
        """
        self.state.ki = max(0.0, float(ki))
    
    # ======================================================================
    # SETTERS - PASS-THROUGH CONTROLS (Driver to Train Model)
    # ======================================================================
    
    def set_doors_left(self, open_: bool) -> None:
        """Set left door state (open/closed)"""
        self.state.doors_left_open = bool(open_)
    
    def set_doors_right(self, open_: bool) -> None:
        """Set right door state (open/closed)"""
        self.state.doors_right_open = bool(open_)
    
    def set_headlights(self, on: bool) -> None:
        """Set headlight state (on/off)"""
        self.state.headlights_on = bool(on)
    
    def set_cabin_lights(self, on: bool) -> None:
        """Set cabin light state (on/off)"""
        self.state.cabin_lights_on = bool(on)
    
    def set_temp_setpoint_c(self, temp_c: float) -> None:
        """
        Set cabin temperature setpoint
        
        Args:
            temp_c: Desired temperature in Celsius
        """
        self.state.temp_setpoint_c = float(temp_c)
    
    # ======================================================================
    # MAIN UPDATE LOOP - Core Control Algorithm
    # ======================================================================
    
    def update(self, dt_s: float) -> None:
        """
        Main control loop - called every tick (typically 10 Hz)
        
        This method implements the PI speed controller and safety logic:
        1. Check emergency brake (highest priority)
        2. Check authority guard (stop if authority <= 0)
        3. Check manual service brake
        4. Compute PI control (if no brakes active)
        5. Apply speed limits
        6. Convert control signal to power command
        
        Args:
            dt_s: Time step in seconds (typically 0.1 for 10 Hz)
        """
        s = self.state
        
        # ========== SAFETY LAYER 1: EMERGENCY BRAKE ==========
        # Emergency brake has absolute priority - stops everything immediately
        if s.emergency_brake_cmd:
            s.emergency_brake_out = True
            s.service_brake_out = False
            s.power_kw = 0.0
            self._reset_integrator()  # Reset PI integrator
            return
        else:
            s.emergency_brake_out = False
        
        # ========== SAFETY LAYER 2: AUTHORITY GUARD ==========
        # If authority is 0 or negative, must stop with service brake
        # (Authority = distance allowed to travel; 0 means "stop here")
        if s.commanded_authority_m <= 0.0:
            s.service_brake_out = True
            s.power_kw = 0.0
            self._reset_integrator()
            return
        
        # ========== SAFETY LAYER 3: MANUAL SERVICE BRAKE ==========
        # Driver can manually activate service brake
        if s.service_brake_cmd:
            s.service_brake_out = True
            s.power_kw = 0.0
            self._reset_integrator()
            return
        else:
            s.service_brake_out = False
        
        # ========== COMPUTE TARGET SPEED ==========
        # In Auto mode: use commanded speed from CTC
        # In Manual mode: use driver's setpoint
        if s.auto_mode:
            target = s.commanded_speed_mps
        else:
            target = s.driver_set_speed_mps
        
        # Apply speed limits (never exceed line limit or controller maximum)
        target = min(target, s.speed_limit_mps, s.MAX_SPEED_MPS)
        target = max(0.0, target)  # Never negative
        
        # ========== PI CONTROLLER ==========
        # Compute error: target speed - actual speed
        err = target - s.actual_speed_mps
        
        # Integrate error over time (with anti-windup)
        # Only integrate positive errors to prevent windup when slowing down
        s._i_err += max(0.0, err) * dt_s
        
        # PI control law: u = Kp * error + Ki * integral(error)
        u = s.kp * err + s.ki * s._i_err
        
        # ========== CONVERT CONTROL SIGNAL TO POWER ==========
        # Map control signal to power in kW
        # Scale factor of 50.0 is tuned for this system
        # Clamp between 0 and 120 kW (max train power)
        s.power_kw = max(0.0, min(120.0, u * 50.0))
    
    def _reset_integrator(self) -> None:
        """
        Reset the PI controller's integral term
        
        Called when brakes are applied to prevent integral windup
        """
        self.state._i_err = 0.0
    
    # ======================================================================
    # TELEMETRY - Output current state for UI display
    # ======================================================================
    
    def get_display_values(self) -> dict:
        """
        Get all controller state for UI display
        
        Returns a dictionary containing all relevant state information
        for display in the UI and logging.
        
        Returns:
            dict: Dictionary with all telemetry values
        """
        s = self.state
        return {
            # Identification
            "train_id": s.train_id,
            
            # Speed and Authority (INPUTS from Train Model)
            "cmd_speed_mph": mps_to_mph(s.commanded_speed_mps),
            "authority_m": s.commanded_authority_m,
            "actual_speed_mph": mps_to_mph(s.actual_speed_mps),
            
            # Driver inputs
            "driver_set_mph": mps_to_mph(s.driver_set_speed_mps),
            "auto_mode": s.auto_mode,
            
            # Control outputs (OUTPUTS to Train Model)
            "power_kw": s.power_kw,
            "service_brake": s.service_brake_out,
            "emergency_brake": s.emergency_brake_out,
            
            # Controller parameters
            "kp": s.kp, 
            "ki": s.ki,
            
            # Pass-through controls (sent to Train Model)
            "doors_left": s.doors_left_open, 
            "doors_right": s.doors_right_open,
            "headlights": s.headlights_on, 
            "cabin_lights": s.cabin_lights_on,
            "temp_c": s.temp_setpoint_c,
        }