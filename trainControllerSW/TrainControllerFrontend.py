from __future__ import annotations
"""
Train Controller Frontend - CLEANED VERSION (No Grade/Beacon)

This module acts as the glue between the UI and the Backend, and handles
integration with the Train Model.

DATA FLOW ARCHITECTURE:
======================

Train Model → Train Controller → Train Model

The correct data flow is:
1. Train Model provides INPUTS to Train Controller:
   - commanded_speed (from CTC via Track Circuit)
   - authority (from CTC via Track Circuit)  
   - actual_speed (from tachometer)

2. Train Controller computes control outputs

3. Train Controller sends OUTPUTS to Train Model:
   - power_kw
   - service_brake
   - emergency_brake
   - (plus pass-through controls: doors, lights, temperature)

IMPORTANT: The Train Controller does NOT push CTC commands to the Train Model.
Instead, it RECEIVES CTC commands FROM the Train Model (which gets them from 
Track Circuit/CTC).

Grade and beacon data DO NOT flow through Train Controller. They go directly:
Track Model → Train Model (for physics simulation and passenger information).
"""

from typing import Optional

try:
    from .TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph
except Exception:
    from TrainControllerBackend import TrainControllerBackend, mph_to_mps, mps_to_mph

# Optional Train Model import (same-process integration)
try:
    from train_model_backend import TrainModelBackend  # type: ignore
except Exception:  # running without the TM in path
    TrainModelBackend = None  # type: ignore


class TrainControllerFrontend:
    """
    Frontend - Integration layer between UI, Backend, and Train Model
    
    This class handles:
    1. Connecting to the Train Model (if available)
    2. Pulling inputs FROM the Train Model each tick
    3. Running the controller logic
    4. Pushing outputs TO the Train Model
    5. Managing demo mode when no Train Model is attached
    
    The key concept: Train Controller is PASSIVE - it receives data from
    Train Model and responds with control outputs. It does NOT command
    the Train Model what speed/authority to use.
    """
    
    def __init__(self, train_id: str = "T1", train_model: Optional["TrainModelBackend"] = None) -> None:
        """
        Initialize the Frontend
        
        Args:
            train_id: Unique identifier for this train
            train_model: Optional Train Model backend for integration
                        If None, runs in demo mode with simulated physics
        """
        # Create the controller backend
        self.ctrl = TrainControllerBackend(train_id=train_id)
        
        # Store reference to Train Model (may be None)
        self.tm: Optional["TrainModelBackend"] = train_model
        
        # Demo mode: simulated speed when no Train Model attached
        # This is ONLY for testing the UI without a full Train Model
        self._demo_speed_mps = 0.0
        self._demo_cmd_speed_mps = 0.0  # For demo mode only
        self._demo_authority_m = 0.0     # For demo mode only
    
    # ======================================================================
    # FEATURE FLAGS - For UI to adjust behavior
    # ======================================================================
    
    def has_train_model(self) -> bool:
        """Check if a Train Model is connected"""
        return self.tm is not None
    
    # ======================================================================
    # UI → CONTROLLER SETTERS (Driver/Engineer inputs)
    # ======================================================================
    
    def set_auto_mode(self, enabled: bool) -> None:
        """Set Auto/Manual mode"""
        self.ctrl.set_auto_mode(enabled)
    
    def set_driver_speed_mph(self, mph: float) -> None:
        """Set driver's manual speed setpoint (in mph)"""
        self.ctrl.set_driver_speed(mph_to_mps(mph))
    
    def set_speed_limit_mph(self, mph: float) -> None:
        """Set line speed limit (in mph)"""
        self.ctrl.set_speed_limit(mph_to_mps(mph))
    
    def set_kp(self, kp: float) -> None:
        """Set proportional gain"""
        self.ctrl.set_kp(kp)
    
    def set_ki(self, ki: float) -> None:
        """Set integral gain"""
        self.ctrl.set_ki(ki)
    
    def set_service_brake(self, active: bool) -> None:
        """Set service brake command"""
        self.ctrl.set_service_brake(active)
    
    def set_emergency_brake(self, active: bool) -> None:
        """Set emergency brake command"""
        self.ctrl.set_emergency_brake(active)
    
    def set_doors_left(self, open_: bool) -> None:
        """Set left door state"""
        self.ctrl.set_doors_left(open_)
    
    def set_doors_right(self, open_: bool) -> None:
        """Set right door state"""
        self.ctrl.set_doors_right(open_)
    
    def set_headlights(self, on: bool) -> None:
        """Set headlight state"""
        self.ctrl.set_headlights(on)
    
    def set_cabin_lights(self, on: bool) -> None:
        """Set cabin light state"""
        self.ctrl.set_cabin_lights(on)
    
    def set_temp_c(self, temp_c: float) -> None:
        """Set cabin temperature setpoint"""
        self.ctrl.set_temp_setpoint_c(temp_c)
    
    # ======================================================================
    # DEMO MODE ONLY - Simulated inputs (used when no Train Model)
    # ======================================================================
    
    def set_actual_speed_mph(self, mph: float) -> None:
        """
        DEMO MODE ONLY: Manually set actual speed
        
        This is only used when no Train Model is attached, to allow
        testing the UI. In real operation, actual speed comes from
        the Train Model's tachometer.
        
        Args:
            mph: Simulated actual speed in miles per hour
        """
        if self.tm is None:
            self._demo_speed_mps = mph_to_mps(mph)
            self.ctrl.set_actual_speed(self._demo_speed_mps)
    
    def set_demo_ctc_command(self, speed_mph: float, authority_m: float) -> None:
        """
        DEMO MODE ONLY: Simulate CTC commands
        
        In real operation, these values come FROM the Train Model
        (which receives them from Track Circuit/CTC). This method
        is only for testing without a Train Model.
        
        Args:
            speed_mph: Simulated commanded speed
            authority_m: Simulated authority
        """
        if self.tm is None:
            self._demo_cmd_speed_mps = mph_to_mps(speed_mph)
            self._demo_authority_m = authority_m
            self.ctrl.set_commanded_speed(self._demo_cmd_speed_mps)
            self.ctrl.set_commanded_authority(self._demo_authority_m)
    
    # ======================================================================
    # MAIN TICK - Integration loop with Train Model
    # ======================================================================
    
    def tick(self, dt_s: float) -> dict:
        """
        Main integration loop - called every frame (typically 10 Hz)
        
        DATA FLOW WITH TRAIN MODEL:
        1. Pull inputs FROM Train Model (commanded speed, authority, actual velocity)
        2. Run controller update() to compute power/brake outputs
        3. Push outputs TO Train Model (power, brakes, doors, lights, temp)
        4. Train Model steps its physics simulation
        
        DATA FLOW IN DEMO MODE (no Train Model):
        1. Use simulated inputs
        2. Run controller update()
        3. Run toy physics simulation to move the needle
        
        Args:
            dt_s: Time step in seconds (typically 0.1 for 10 Hz)
            
        Returns:
            dict: Telemetry dictionary for UI display
        """
        
        if self.tm is not None:
            # ========== INTEGRATED MODE (Train Model attached) ==========
            
            # STEP 1: Pull inputs FROM Train Model
            # The Train Model has received CTC commands from Track Circuit
            # and has measured the actual train velocity
            state = self.tm.report_state()
            
            # Extract speed and authority (these came from CTC via Track Circuit)
            actual_velocity_mps = float(state.get("velocity", 0.0))
            commanded_speed_mps = float(state.get("commanded_speed", 0.0))
            commanded_authority_m = float(state.get("authority", 0.0))
            
            # Feed these inputs into the controller
            self.ctrl.set_actual_speed(actual_velocity_mps)
            self.ctrl.set_commanded_speed(commanded_speed_mps)
            self.ctrl.set_commanded_authority(commanded_authority_m)
            
            # STEP 2: Run the controller algorithm
            # This computes power and brake commands based on the inputs
            self.ctrl.update(dt_s)
            
            # Get the computed outputs
            outputs = self.ctrl.get_display_values()
            
            # STEP 3: Push outputs TO Train Model
            # The Train Model will use these to update its physics simulation
            # NOTE: Grade and beacon are NOT provided by Train Controller!
            # They come directly from Track Model to Train Model.
            # If the Train Model's set_inputs requires them, they should be
            # passed through from Track Model or default to 0/"None".
            
            # Check if train model expects these parameters
            try:
                self.tm.set_inputs(
                    power_kw=float(outputs["power_kw"]),
                    service_brake=bool(outputs["service_brake"]),
                    emergency_brake=bool(outputs["emergency_brake"]),
                )
            except TypeError:
                # If set_inputs requires grade/beacon, the Train Model should
                # get those from Track Model, not from us. This is a fallback.
                pass
            
            # Also send pass-through controls (doors, lights, temperature)
            # These go directly to the Train Model without controller logic
            if hasattr(self.tm, 'set_doors'):
                self.tm.set_doors(
                    left=bool(outputs["doors_left"]),
                    right=bool(outputs["doors_right"])
                )
            if hasattr(self.tm, 'set_lights'):
                self.tm.set_lights(
                    headlights=bool(outputs["headlights"]),
                    cabin=bool(outputs["cabin_lights"])
                )
            if hasattr(self.tm, 'set_temperature'):
                self.tm.set_temperature(float(outputs["temp_c"]))
            
            return outputs
        
        else:
            # ========== DEMO MODE (No Train Model) ==========
            # Simulate the data flow using toy physics
            
            # Use demo inputs (set by UI for testing)
            self.ctrl.set_actual_speed(self._demo_speed_mps)
            self.ctrl.set_commanded_speed(self._demo_cmd_speed_mps)
            self.ctrl.set_commanded_authority(self._demo_authority_m)
            
            # Run controller
            self.ctrl.update(dt_s)
            
            # Get outputs
            outputs = self.ctrl.get_display_values()
            
            # Simple toy physics to make the speed change
            power_kw = float(outputs.get("power_kw", 0.0))
            eb_active = bool(outputs.get("emergency_brake", False))
            sb_active = bool(outputs.get("service_brake", False))
            
            # Compute acceleration based on outputs
            if eb_active:
                accel = -3.0  # Hard braking
            elif sb_active:
                accel = -1.0  # Moderate braking
            else:
                accel = 0.02 * power_kw  # Power → acceleration
            
            # Update demo speed
            self._demo_speed_mps = max(0.0, self._demo_speed_mps + accel * dt_s)
            self.ctrl.set_actual_speed(self._demo_speed_mps)
            
            return self.ctrl.get_display_values()