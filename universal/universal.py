"""
Universal data structures and conversion functions for the train control system.
"""
from dataclasses import dataclass
from enum import Enum

import sys
sys.path.append('../')

class SignalState(Enum):
    """Enumeration of signal states for track segments."""
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    SUPERGREEN = "super_green"

@dataclass
class TrainCommand:
    """Command packet for per-train instructions.
    
    Attributes:
        train_id: ID of the target train.
        commanded_speed: Speed command for the train in m/s.
        authority: Movement authority for the train in meters.
    """
    commanded_speed: int
    authority: int

class ConversionFunctions:
    """Holds conversion factors for various units."""
    
    @staticmethod
    def mph_to_mps(mph):
        return mph * 0.44704  # conversion factor
    
    @staticmethod
    def mps_to_mph(mps):
        return mps / 0.44704  # conversion factor
    
    @staticmethod
    def feet_to_meters(feet):
        return feet * 0.3048  # conversion factor
    
    @staticmethod
    def meters_to_feet(meters):
        return meters / 0.3048  # conversion factor
    
    @staticmethod
    def celsius_to_fahrenheit(celsius):
        return (celsius * 9/5) + 32  # conversion formula
    
    @staticmethod
    def fahrenheit_to_celsius(fahrenheit):
        return (fahrenheit - 32) * 5/9  # conversion formula
    
    @staticmethod
    def meters_to_yards(meters):
        """Convert meters to yards."""
        return meters * 1.0936132983377078

    @staticmethod
    def yards_to_meters(yards):
        """Convert yards to meters."""
        return yards / 1.0936132983377078
    