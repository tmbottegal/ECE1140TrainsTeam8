""" 

 This is the Train Controller Front End.

"""

from __future__ import annotations
from typing import Optional, Dict, Callable
from trainControllerBackend import trainControllerBackend

class TrainControllerFrontend:
    def __init__(self, controller: Optional[trainControllerBackend] = None) -> None:
        self.ctrl = controller or trainControllerBackend()
        self.send_to_train_model: Optional[Callable[[Dict], None]] = None
        self.publish_state: Optional[Callable[[Dict], None]] = None


      # CTC -> Controller?
    def set_ctc_command(self, speed_mps: float, authority: bool) -> None:
        self.ctrl.set_commanded_speed(speed_mps)
        self.ctrl.set_commanded_authority(authority)

      # Driver/UI -> Controller
    def set_service_brake(self, active: bool) -> None:
        self.ctrl.set_service_brake(active)

    def set_emergency_brake(self, active: bool) -> None:
        self.ctrl.set_emergency_brake(active)

    def set_lights(self, on: bool) -> None:
        self.ctrl.set_lights(on)

    def ingest_measured_speed(self, speed_mps: float) -> None:
        self.ctrl.update_actual_speed(speed_mps)

    def step(self, dt: float) -> Dict:
        
        outputs = self.ctrl.tick(dt)
        if self.send_to_train_model:
            self.send_to_train_model(outputs)
        if self.publish_state:
            self.publish_state(self.ctrl.snapshot() | outputs)
        return outputs
    
    def snapshot(self) -> Dict:
        return self.ctrl.snapshot()
    

