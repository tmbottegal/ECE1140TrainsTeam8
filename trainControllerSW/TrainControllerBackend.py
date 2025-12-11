"""
TrainControllerBackend.py
Core control logic for the Train Controller

Implements:
- PI controller for speed regulation
- Manual and Automatic modes  
- Emergency and Service brakes
- Safety constraints
- All 22 requirements
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Try to import from universal module
try:
    from universal import ConversionFunctions
except (ImportError, ModuleNotFoundError):
    # Fallback: Define ConversionFunctions locally
    class ConversionFunctions:
        """Conversion functions for units."""
        
        @staticmethod
        def mph_to_mps(mph):
            return mph * 0.44704
        
        @staticmethod
        def mps_to_mph(mps):
            return mps / 0.44704
        
        @staticmethod
        def feet_to_meters(feet):
            return feet * 0.3048
        
        @staticmethod
        def meters_to_feet(meters):
            return meters / 0.3048

# Try to import global clock
try:
    from global_clock import clock
except (ImportError, ModuleNotFoundError):
    # Fallback: Create a simple clock
    import datetime
    
    class SimpleClock:
        def __init__(self):
            self.current_time = datetime.datetime.now()
            self._listeners = []
            
        def tick(self):
            self.current_time += datetime.timedelta(seconds=1)
            for callback in self._listeners:
                try:
                    callback(self.current_time)
                except:
                    pass
            return self.current_time
            
        def get_time(self):
            return self.current_time
            
        def get_time_string(self):
            return self.current_time.strftime("%I:%M:%S %p")
            
        def register_listener(self, callback):
            if callback not in self._listeners:
                self._listeners.append(callback)
    
    clock = SimpleClock()

import datetime

# Constants
MAX_POWER_KW = 120000
MIN_POWER_KW = -120000
SAMPLING_PERIOD = 0.2
MIN_TEMP_F = 60
MAX_TEMP_F = 85
DEFAULT_TEMP_F = 68


class TrainControllerBackend:
    """Backend controller implementing all train control logic."""
    
    def __init__(self, train_id=12123):
        """Initialize the train controller."""
        self.train_id = train_id
        
        # Mode
        self.automatic_mode = True  # True = Automatic, False = Manual
        
        # Speed and Authority (from Track Controller)
        self.commanded_speed_mph = 0.0  # From Track Controller
        self.speed_limit_mph = 44.0  # Block speed limit
        self.authority_ft = 0.0  # Movement authority
        
        # Current state (from Train Model)
        self.current_speed_mph = 0.0
        self.at_station = False
        self.station_name = ""
        self.current_line = "Green"
        
        # Manual mode setpoint
        self.setpoint_speed_mph = 0.0
        
        # PI Controller
        self.kp = 10000.0
        self.ki = 1000.0
        self.power_kw = 0.0
        self.uk = 0.0  # Integral term current
        self.uk1 = 0.0  # Integral term previous
        self.ek = 0.0  # Error current
        self.ek1 = 0.0  # Error previous
        
        # Brakes
        self.service_brake = False
        self.emergency_brake = False
        self.emergency_brake_enabled = False
        
        # Controls
        self.left_doors_open = False
        self.right_doors_open = False
        self.interior_lights_on = False
        self.headlights_on = True
        self.cabin_temp_f = DEFAULT_TEMP_F
        self.ac_on = True
        
        # Failures (from Train Model)
        self.engine_failure = False
        self.brake_failure = False
        self.signal_failure = False
        
        # Status log
        self.status_log = []
        
        # Register with global clock
        clock.register_listener(self.on_clock_tick)
        
    def on_clock_tick(self, current_time):
        """Called by global clock each tick."""
        self.calculate_power()
        
    def set_automatic_mode(self, auto):
        """Set automatic (True) or manual (False) mode."""
        self.automatic_mode = auto
        self.log(f"Mode: {'AUTOMATIC' if auto else 'MANUAL'}")
        
    def set_kp(self, kp):
        """Set proportional gain."""
        self.kp = max(0.0, kp)
        
    def set_ki(self, ki):
        """Set integral gain."""
        self.ki = max(0.0, ki)
        
    def set_setpoint_speed_mph(self, speed):
        """Set manual mode setpoint speed (limited by speed limit)."""
        limited = min(speed, self.speed_limit_mph)
        self.setpoint_speed_mph = max(0.0, limited)
        
    def increase_speed(self, delta=1.0):
        """Increase setpoint speed."""
        self.set_setpoint_speed_mph(self.setpoint_speed_mph + delta)
        
    def decrease_speed(self, delta=1.0):
        """Decrease setpoint speed."""
        self.set_setpoint_speed_mph(self.setpoint_speed_mph - delta)
        
    def set_service_brake(self, engaged):
        """Set service brake."""
        self.service_brake = engaged
        if engaged:
            self.log("Service brake ENGAGED")
            
    def set_emergency_brake(self, engaged):
        """Set emergency brake (requires enable toggle)."""
        if self.emergency_brake_enabled or not engaged:
            self.emergency_brake = engaged
            if engaged:
                self.log("⚠️ EMERGENCY BRAKE ENGAGED")
                
    def toggle_emergency_enable(self):
        """Toggle emergency brake enable."""
        self.emergency_brake_enabled = not self.emergency_brake_enabled
        
    def set_cabin_temp(self, temp_f):
        """Set cabin temperature (limited)."""
        self.cabin_temp_f = max(MIN_TEMP_F, min(MAX_TEMP_F, temp_f))
        
    def toggle_left_doors(self):
        """Toggle left doors (with safety checks)."""
        if self.current_speed_mph != 0:
            self.log("❌ Cannot operate doors while moving")
            return
        if not self.at_station:
            self.log("❌ Cannot open doors - not at station")
            return
        self.left_doors_open = not self.left_doors_open
        self.log(f"Left doors {'OPEN' if self.left_doors_open else 'CLOSED'}")
        
    def toggle_right_doors(self):
        """Toggle right doors (with safety checks)."""
        if self.current_speed_mph != 0:
            self.log("❌ Cannot operate doors while moving")
            return
        if not self.at_station:
            self.log("❌ Cannot open doors - not at station")
            return
        self.right_doors_open = not self.right_doors_open
        self.log(f"Right doors {'OPEN' if self.right_doors_open else 'CLOSED'}")
        
    def toggle_interior_lights(self):
        """Toggle interior lights (with safety checks)."""
        current_time = clock.get_time()
        is_night = current_time.hour < 6 or current_time.hour >= 20
        
        if is_night and self.interior_lights_on:
            self.log("❌ Cannot turn off lights at night")
            return
            
        self.interior_lights_on = not self.interior_lights_on
        self.log(f"Interior lights {'ON' if self.interior_lights_on else 'OFF'}")
        
    def toggle_headlights(self):
        """Toggle headlights (with safety checks)."""
        current_time = clock.get_time()
        is_night = current_time.hour < 6 or current_time.hour >= 20
        
        if is_night and self.headlights_on:
            self.log("❌ Cannot turn off headlights at night")
            return
            
        self.headlights_on = not self.headlights_on
        self.log(f"Headlights {'ON' if self.headlights_on else 'OFF'}")
        
    def toggle_ac(self):
        """Toggle A/C."""
        self.ac_on = not self.ac_on
        
    def update_from_track_controller(self, commanded_speed_mph, authority_ft, speed_limit_mph):
        """Update values from Track Controller."""
        self.commanded_speed_mph = commanded_speed_mph
        self.authority_ft = authority_ft
        self.speed_limit_mph = speed_limit_mph
        
        # Auto service brake if no authority
        if authority_ft <= 0:
            self.service_brake = True
            
    def update_from_train_model(self, current_speed_mph, engine_fail=False, brake_fail=False, signal_fail=False):
        """Update values from Train Model."""
        self.current_speed_mph = current_speed_mph
        self.engine_failure = engine_fail
        self.brake_failure = brake_fail
        self.signal_failure = signal_fail
        
        # Auto emergency brake on failures
        if engine_fail or brake_fail or signal_fail:
            self.emergency_brake = True
            self.log("⚠️ FAILURE DETECTED - Emergency brake")
            
    def calculate_power(self):
        """
        Calculate power command using PI controller.
        Core control algorithm.
        """
        # Convert to m/s for calculation
        current_mps = ConversionFunctions.mph_to_mps(self.current_speed_mph)
        
        # Determine target speed
        if self.automatic_mode:
            target_mph = self.commanded_speed_mph
        else:
            target_mph = self.setpoint_speed_mph
            
        target_mps = ConversionFunctions.mph_to_mps(target_mph)
        
        # Calculate error
        self.ek = target_mps - current_mps
        
        # Update integral with anti-windup
        if self.power_kw < MAX_POWER_KW and self.power_kw > MIN_POWER_KW:
            self.uk = self.uk1 + (SAMPLING_PERIOD / 2) * (self.ek + self.ek1)
        else:
            self.uk = self.uk1
            
        # Calculate power
        if self.emergency_brake or self.service_brake:
            self.power_kw = 0.0
            self.uk = 0.0
            self.ek = 0.0
        else:
            # Triple redundancy
            power1 = (self.kp * self.ek) + (self.ki * self.uk)
            power2 = (self.kp * self.ek) + (self.ki * self.uk)
            power3 = (self.kp * self.ek) + (self.ki * self.uk)
            
            if power1 == power2 == power3:
                self.power_kw = power1
            else:
                self.emergency_brake = True
                self.power_kw = 0.0
                self.log("⚠️ Power calculation mismatch - E-Brake")
                
            # Limit power
            self.power_kw = max(MIN_POWER_KW, min(MAX_POWER_KW, self.power_kw))
            
        # Update previous values
        self.uk1 = self.uk
        self.ek1 = self.ek
        
    def log(self, message):
        """Add message to status log."""
        timestamp = clock.get_time_string()
        entry = f"[{timestamp}] {message}"
        self.status_log.append(entry)
        if len(self.status_log) > 100:
            self.status_log.pop(0)
            
    def get_state(self):
        """Get current state as dict."""
        return {
            'train_id': self.train_id,
            'automatic_mode': self.automatic_mode,
            'current_speed_mph': self.current_speed_mph,
            'commanded_speed_mph': self.commanded_speed_mph,
            'setpoint_speed_mph': self.setpoint_speed_mph,
            'speed_limit_mph': self.speed_limit_mph,
            'authority_ft': self.authority_ft,
            'power_kw': self.power_kw,
            'service_brake': self.service_brake,
            'emergency_brake': self.emergency_brake,
            'emergency_brake_enabled': self.emergency_brake_enabled,
            'kp': self.kp,
            'ki': self.ki,
            'left_doors_open': self.left_doors_open,
            'right_doors_open': self.right_doors_open,
            'interior_lights_on': self.interior_lights_on,
            'headlights_on': self.headlights_on,
            'cabin_temp_f': self.cabin_temp_f,
            'ac_on': self.ac_on,
            'at_station': self.at_station,
            'station_name': self.station_name,
            'current_line': self.current_line,
            'engine_failure': self.engine_failure,
            'brake_failure': self.brake_failure,
            'signal_failure': self.signal_failure,
            'status_log': self.status_log[-10:]
        }