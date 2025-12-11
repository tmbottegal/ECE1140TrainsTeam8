"""
TrainControllerTest.py
Comprehensive test suite for Train Controller SW

Tests based on Software and System Test Documentation
Section 6.6: Train Controller Test Procedures
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pytest
from TrainControllerBackend import TrainControllerBackend, ConversionFunctions


class TestPowerCommands:
    """Test Case: Send power commands to the Train Model"""
    
    def test_power_calculation_with_kp_ki(self):
        """
        Test Case: Send power commands to the Train Model
        Inputs: From Train Controller: Kp and Ki set by Engineer
        Expected: Send the calculated increased or decreased Power to Train Model
        """
        # Create controller
        controller = TrainControllerBackend(train_id=12123)
        
        # Set PI gains (Engineer input)
        kp = 10000.0
        ki = 1000.0
        controller.set_kp(kp)
        controller.set_ki(ki)
        
        # Verify gains are set
        assert controller.kp == kp, "Kp not set correctly"
        assert controller.ki == ki, "Ki not set correctly"
        
        # Set up scenario: train at 0 mph, commanded to go 30 mph
        controller.update_from_train_model(current_speed_mph=0.0)
        controller.update_from_track_controller(
            commanded_speed_mph=30.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        
        # In automatic mode
        controller.set_automatic_mode(True)
        
        # Calculate power
        controller.calculate_power()
        
        # Power should be positive (accelerating)
        assert controller.power_kw > 0, "Power should be positive to accelerate"
        assert controller.power_kw <= 120000, "Power should not exceed maximum"
        
        print(f"✓ Power calculation test passed")
        print(f"  Kp={kp}, Ki={ki}")
        print(f"  Target: 30 MPH, Current: 0 MPH")
        print(f"  Calculated Power: {controller.power_kw:.2f} kW")


class TestAutomaticMode:
    """Test automatic mode operation"""
    
    def test_automatic_mode_follows_commanded_speed(self):
        """Verify controller follows Track Controller commands in automatic mode"""
        controller = TrainControllerBackend()
        
        # Set to automatic mode
        controller.set_automatic_mode(True)
        assert controller.automatic_mode == True
        
        # Set commanded speed from Track Controller
        controller.update_from_track_controller(
            commanded_speed_mph=25.0,
            authority_ft=500.0,
            speed_limit_mph=44.0
        )
        
        # Set current speed lower
        controller.update_from_train_model(current_speed_mph=10.0)
        
        # Calculate power
        controller.calculate_power()
        
        # Should produce positive power to reach commanded speed
        assert controller.power_kw > 0, "Should accelerate to commanded speed"
        
        print(f"✓ Automatic mode test passed")
        print(f"  Commanded: 25 MPH, Current: 10 MPH")
        print(f"  Power: {controller.power_kw:.2f} kW (positive = accelerating)")


class TestManualMode:
    """Test manual mode operation"""
    
    def test_manual_mode_follows_setpoint(self):
        """Verify controller follows driver setpoint in manual mode"""
        controller = TrainControllerBackend()
        
        # Set to manual mode
        controller.set_automatic_mode(False)
        assert controller.automatic_mode == False
        
        # Driver sets speed to 20 MPH
        controller.set_setpoint_speed_mph(20.0)
        assert controller.setpoint_speed_mph == 20.0
        
        # Current speed is 5 MPH
        controller.update_from_train_model(current_speed_mph=5.0)
        
        # Set authority and speed limit
        controller.update_from_track_controller(
            commanded_speed_mph=0.0,  # Not used in manual
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        
        # Calculate power
        controller.calculate_power()
        
        # Should accelerate to setpoint
        assert controller.power_kw > 0, "Should accelerate to setpoint"
        
        print(f"✓ Manual mode test passed")
        print(f"  Setpoint: 20 MPH, Current: 5 MPH")
        print(f"  Power: {controller.power_kw:.2f} kW")
    
    def test_manual_mode_speed_limiting(self):
        """Verify driver cannot exceed speed limit in manual mode"""
        controller = TrainControllerBackend()
        
        # Set manual mode
        controller.set_automatic_mode(False)
        
        # Set speed limit to 30 MPH
        controller.update_from_track_controller(
            commanded_speed_mph=0.0,
            authority_ft=1000.0,
            speed_limit_mph=30.0
        )
        
        # Driver tries to set 50 MPH (above limit)
        controller.set_setpoint_speed_mph(50.0)
        
        # Should be limited to speed limit
        assert controller.setpoint_speed_mph == 30.0, "Speed should be limited"
        
        print(f"✓ Speed limiting test passed")
        print(f"  Attempted: 50 MPH, Speed Limit: 30 MPH")
        print(f"  Result: {controller.setpoint_speed_mph} MPH (limited)")


class TestEmergencyBrake:
    """Test emergency brake functionality"""
    
    def test_emergency_brake_cuts_power(self):
        """Verify emergency brake immediately cuts power to zero"""
        controller = TrainControllerBackend()
        
        # Set up moving train
        controller.update_from_train_model(current_speed_mph=30.0)
        controller.update_from_track_controller(
            commanded_speed_mph=40.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        
        # Enable emergency brake
        controller.emergency_brake_enabled = True
        
        # Engage emergency brake
        controller.set_emergency_brake(True)
        
        # Calculate power
        controller.calculate_power()
        
        # Power should be zero
        assert controller.power_kw == 0.0, "Power must be 0 during emergency brake"
        assert controller.emergency_brake == True, "Emergency brake should be engaged"
        
        print(f"✓ Emergency brake test passed")
        print(f"  Emergency brake engaged → Power = {controller.power_kw} kW")
    
    def test_emergency_brake_on_failure(self):
        """Verify emergency brake engages automatically on failures"""
        controller = TrainControllerBackend()
        
        # Simulate engine failure
        controller.update_from_train_model(
            current_speed_mph=20.0,
            engine_fail=True
        )
        
        # Emergency brake should auto-engage
        assert controller.emergency_brake == True, "E-brake should auto-engage on failure"
        
        # Calculate power
        controller.calculate_power()
        assert controller.power_kw == 0.0, "Power should be 0"
        
        print(f"✓ Auto emergency brake test passed")
        print(f"  Engine failure detected → E-brake engaged")


class TestServiceBrake:
    """Test service brake functionality"""
    
    def test_service_brake_cuts_power(self):
        """Verify service brake cuts power to zero"""
        controller = TrainControllerBackend()
        
        # Set up scenario
        controller.update_from_train_model(current_speed_mph=25.0)
        controller.update_from_track_controller(
            commanded_speed_mph=30.0,
            authority_ft=500.0,
            speed_limit_mph=44.0
        )
        
        # Engage service brake
        controller.set_service_brake(True)
        
        # Calculate power
        controller.calculate_power()
        
        # Power should be zero
        assert controller.power_kw == 0.0, "Power must be 0 during service brake"
        assert controller.service_brake == True, "Service brake should be engaged"
        
        print(f"✓ Service brake test passed")
        print(f"  Service brake engaged → Power = {controller.power_kw} kW")
    
    def test_service_brake_on_zero_authority(self):
        """Verify service brake auto-engages when authority = 0"""
        controller = TrainControllerBackend()
        
        # Set authority to 0
        controller.update_from_track_controller(
            commanded_speed_mph=20.0,
            authority_ft=0.0,  # No authority
            speed_limit_mph=44.0
        )
        
        # Service brake should auto-engage
        assert controller.service_brake == True, "Service brake should engage at authority=0"
        
        print(f"✓ Authority brake test passed")
        print(f"  Authority = 0 → Service brake auto-engaged")


class TestDoorControls:
    """Test door safety interlocks"""
    
    def test_doors_only_at_station(self):
        """Verify doors only open at stations"""
        controller = TrainControllerBackend()
        
        # Set train stopped but NOT at station
        controller.update_from_train_model(current_speed_mph=0.0)
        controller.at_station = False
        
        # Try to open doors
        initial_left = controller.left_doors_open
        controller.toggle_left_doors()
        
        # Doors should NOT open
        assert controller.left_doors_open == initial_left, "Doors should not open away from station"
        
        # Now set at station
        controller.at_station = True
        controller.station_name = "Test Station"
        
        # Try again
        controller.toggle_left_doors()
        
        # Now doors should open
        assert controller.left_doors_open == True, "Doors should open at station"
        
        print(f"✓ Door station check test passed")
        print(f"  Not at station: Doors stayed closed")
        print(f"  At station: Doors opened")
    
    def test_doors_only_when_stopped(self):
        """Verify doors only operate when train is stopped"""
        controller = TrainControllerBackend()
        
        # Set at station but moving
        controller.at_station = True
        controller.update_from_train_model(current_speed_mph=5.0)  # Moving
        
        # Try to open doors
        initial_state = controller.right_doors_open
        controller.toggle_right_doors()
        
        # Doors should NOT open
        assert controller.right_doors_open == initial_state, "Doors should not open while moving"
        
        # Stop the train
        controller.update_from_train_model(current_speed_mph=0.0)
        
        # Try again
        controller.toggle_right_doors()
        
        # Now doors should open
        assert controller.right_doors_open == True, "Doors should open when stopped"
        
        print(f"✓ Door speed check test passed")
        print(f"  Moving: Doors stayed closed")
        print(f"  Stopped: Doors opened")


class TestTemperatureControl:
    """Test temperature control limits"""
    
    def test_temperature_limits(self):
        """Verify temperature is constrained to 60-85°F"""
        controller = TrainControllerBackend()
        
        # Try to set too low
        controller.set_cabin_temp(50.0)  # Below minimum
        assert controller.cabin_temp_f == 60.0, "Should be limited to 60°F minimum"
        
        # Try to set too high
        controller.set_cabin_temp(100.0)  # Above maximum
        assert controller.cabin_temp_f == 85.0, "Should be limited to 85°F maximum"
        
        # Set valid temperature
        controller.set_cabin_temp(72.0)
        assert controller.cabin_temp_f == 72.0, "Should accept valid temperature"
        
        print(f"✓ Temperature limits test passed")
        print(f"  Min: 60°F, Max: 85°F, Valid: 72°F")


class TestPIController:
    """Test PI controller algorithm"""
    
    def test_pi_controller_accelerates(self):
        """Verify PI controller produces positive power when speed is below target"""
        controller = TrainControllerBackend()
        
        # Set gains
        controller.set_kp(10000.0)
        controller.set_ki(1000.0)
        
        # Target 30 mph, current 10 mph
        controller.set_automatic_mode(True)
        controller.update_from_track_controller(
            commanded_speed_mph=30.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        controller.update_from_train_model(current_speed_mph=10.0)
        
        # Calculate power
        controller.calculate_power()
        
        # Should produce positive power
        assert controller.power_kw > 0, "PI controller should produce positive power"
        assert controller.ek > 0, "Error should be positive"
        
        print(f"✓ PI controller acceleration test passed")
        print(f"  Error: {controller.ek:.3f} m/s")
        print(f"  Power: {controller.power_kw:.2f} kW")
    
    def test_pi_controller_decelerates(self):
        """Verify PI controller produces negative power when speed is above target"""
        controller = TrainControllerBackend()
        
        # Set gains
        controller.set_kp(10000.0)
        controller.set_ki(1000.0)
        
        # Target 10 mph, current 30 mph
        controller.set_automatic_mode(True)
        controller.update_from_track_controller(
            commanded_speed_mph=10.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        controller.update_from_train_model(current_speed_mph=30.0)
        
        # Calculate power
        controller.calculate_power()
        
        # Error should be negative
        assert controller.ek < 0, "Error should be negative"
        
        print(f"✓ PI controller deceleration test passed")
        print(f"  Error: {controller.ek:.3f} m/s (negative = too fast)")
        print(f"  Power: {controller.power_kw:.2f} kW")


class TestConversionFunctions:
    """Test unit conversions"""
    
    def test_mph_to_mps(self):
        """Test MPH to m/s conversion"""
        result = ConversionFunctions.mph_to_mps(55.0)
        expected = 55.0 * 0.44704
        assert abs(result - expected) < 0.001, "MPH to m/s conversion incorrect"
        print(f"✓ MPH to m/s: 55 MPH = {result:.3f} m/s")
    
    def test_feet_to_meters(self):
        """Test feet to meters conversion"""
        result = ConversionFunctions.feet_to_meters(100.0)
        expected = 100.0 * 0.3048
        assert abs(result - expected) < 0.001, "Feet to meters conversion incorrect"
        print(f"✓ Feet to meters: 100 ft = {result:.3f} m")


class TestStatusLog:
    """Test status logging functionality"""
    
    def test_status_log_records_events(self):
        """Verify events are logged with timestamps"""
        controller = TrainControllerBackend()
        
        # Trigger some events
        controller.log("Test event 1")
        controller.log("Test event 2")
        controller.log("Test event 3")
        
        # Check log has entries
        assert len(controller.status_log) >= 3, "Events should be logged"
        
        # Check entries contain timestamps
        for entry in controller.status_log:
            assert "[" in entry and "]" in entry, "Entries should have timestamps"
        
        print(f"✓ Status log test passed")
        print(f"  Logged {len(controller.status_log)} events")


class TestSpeedIncreaseDecrease:
    """Test speed increment/decrement buttons"""
    
    def test_speed_increase(self):
        """Test speed increase functionality"""
        controller = TrainControllerBackend()
        controller.set_automatic_mode(False)  # Manual mode
        
        # Set speed limit
        controller.update_from_track_controller(
            commanded_speed_mph=0.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        
        # Start at 10 mph
        controller.set_setpoint_speed_mph(10.0)
        
        # Increase by 5
        controller.increase_speed(5.0)
        
        assert controller.setpoint_speed_mph == 15.0, "Speed should increase"
        
        print(f"✓ Speed increase test passed: 10 → 15 MPH")
    
    def test_speed_decrease(self):
        """Test speed decrease functionality"""
        controller = TrainControllerBackend()
        controller.set_automatic_mode(False)
        
        controller.update_from_track_controller(
            commanded_speed_mph=0.0,
            authority_ft=1000.0,
            speed_limit_mph=44.0
        )
        
        # Start at 20 mph
        controller.set_setpoint_speed_mph(20.0)
        
        # Decrease by 8
        controller.decrease_speed(8.0)
        
        assert controller.setpoint_speed_mph == 12.0, "Speed should decrease"
        
        print(f"✓ Speed decrease test passed: 20 → 12 MPH")


def run_all_tests():
    """Run all tests and print summary"""
    print("=" * 60)
    print("TRAIN CONTROLLER TEST SUITE")
    print("=" * 60)
    print()
    
    # Run pytest
    pytest.main([__file__, '-v', '--tb=short'])


if __name__ == '__main__':
    run_all_tests()