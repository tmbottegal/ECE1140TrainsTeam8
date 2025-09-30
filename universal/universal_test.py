import pytest
from universal import ConversionFunctions

def test_mph_to_mps():
    """Test mph to m/s conversion."""
    result = ConversionFunctions.mph_to_mps(55)
    expected = 55 * 0.44704
    assert abs(result - expected) < 0.001
def test_mps_to_mph():
    """Test m/s to mph conversion."""
    result = ConversionFunctions.mps_to_mph(24.5872)
    expected = 24.5872 / 0.44704
    assert abs(result - expected) < 0.001

def test_feet_to_meters():
    """Test feet to meters conversion."""
    result = ConversionFunctions.feet_to_meters(100)
    expected = 100 * 0.3048
    assert abs(result - expected) < 0.001

def test_meters_to_feet():
    """Test meters to feet conversion."""
    result = ConversionFunctions.meters_to_feet(30.48)
    expected = 30.48 / 0.3048
    assert abs(result - expected) < 0.001

def test_celsius_to_fahrenheit():
    """Test Celsius to Fahrenheit conversion."""
    result = ConversionFunctions.celsius_to_fahrenheit(0)
    expected = 32
    assert result == expected
    
    result = ConversionFunctions.celsius_to_fahrenheit(100)
    expected = 212
    assert result == expected

def test_fahrenheit_to_celsius():
    """Test Fahrenheit to Celsius conversion."""
    result = ConversionFunctions.fahrenheit_to_celsius(32)
    expected = 0
    assert result == expected
    
    result = ConversionFunctions.fahrenheit_to_celsius(212)
    expected = 100
    assert result == expected

if __name__ == "__main__":
    pytest.main([__file__, "-v"])