from enum import StrEnum, auto
from typing import Dict, List, Optional

from openenv.core.env_server import Action, Observation, State

class Severity(StrEnum):
    LOW = auto()
    MEDIUM = auto()  # ie, the value of auto() will be "medium"
    HIGH = auto()
    CRITICAL = auto()


# --------------------------------------------------------------------------------
# The Resource Types
# --------------------------------------------------------------------------------
class DoctorType(StrEnum):
    ER = auto()
    SURGEON = auto()
    RADIOLOGIST = auto()
    ICU = auto()


class ScannerType(StrEnum):
    XRAY = auto()
    CT = auto()
    MRI = auto()


class BedType(StrEnum):
    GENERAL = auto()
    ICU = auto()


class NurseType(StrEnum):
    GENERAL = auto()
    ICU = auto()
    OR = auto()


# --------------------------------------------------------------------------------
# The States
# --------------------------------------------------------------------------------
class Patient(State):
    patient_id: str
    arrival_hour: int
    severity: Severity
    condition_score: float = 0.0 # higher score means more severe condition
    max_wait_hours: int = 4 # should we consider patient dead after this ???
    waited_hours: int = 0

    required_doctor: DoctorType = DoctorType.ER
    required_nurse_type: NurseType = NurseType.GENERAL
    required_nurses: int = 1
    required_bed_type: BedType = BedType.GENERAL

    requires_scanner: bool = False
    required_scanner: Optional[ScannerType] = None

    requires_operation: bool = False
    operation_duration_hours: int = 0

    treatment_remaining_hours: int = 1 # how many more hours of treatment is needed ??? Is this meaningful in reality ???

class DoctorResource(State):
    doctor_id: str
    doctor_type: DoctorType
    busy_until_hour: int = 0

class NurseResource(State):
    nurse_id: str
    nurse_type: NurseType
    busy_until_hour: int = 0

class ScannerResource(State):
    scanner_id: str
    scanner_type: ScannerType
    busy_until_hour: int = 0

class BedResource(State):
    bed_id: str
    bed_type: BedType
    occupied_by_patient_id: Optional[str] = None

class OperatingRoomResource(State):
    room_id: str
    busy_until_hour: int = 0

class HospitalMetrics(State):
    treated_patients: int = 0
    discharged_patients: int = 0
    deceased_patients: int = 0
    total_wait_time_hours: int = 0
    objective_score: float = 0.0

class HospitalState(State):
    current_hour: int = 0
    horizon_hours: int = 24

    waiting_patients: List[Patient] = []
    active_patients: List[Patient] = []
    discharged_patients: List[Patient] = []
    deceased_patients: List[Patient] = []

    doctors: List[DoctorResource] = []
    nurses: List[NurseResource] = []
    scanners: List[ScannerResource] = []
    beds: List[BedResource] = []
    operating_rooms: List[OperatingRoomResource] = []

    metrics: HospitalMetrics = HospitalMetrics()


# --------------------------------------------------------------------------------
# The Actions, Observations
# --------------------------------------------------------------------------------
class ResourceAssignment(Action):
    patient_id: str
    doctor_ids: List[str] = []
    nurse_ids: List[str] = []
    scanner_id: Optional[str] = None
    bed_id: Optional[str] = None
    operating_room_id: Optional[str] = None

class HospitalAction(Action):
    assignments: List[ResourceAssignment] = []


class HospitalObservation(Observation):
    hour: int = 0
    waiting_patients: int = 0
    critical_waiting_patients: int = 0
    resources_free: Dict[str, int] = {}
    queue_by_severity: Dict[str, int] = {}