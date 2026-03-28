from typing import List
from openenv.core.env_server import Action, Observation, State

class HospitalAction(Action):
    work_on_patient: str

class HospitalObservation(Observation):
    patient_state: str = ""

class HospitalState(State):
    patients: List[str] = []