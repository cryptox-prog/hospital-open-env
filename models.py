from enum import StrEnum, auto
from typing import Dict, List, Optional

from openenv.core.env_server import Action, Observation, State

# --------------------------------------------------------------------------------
# The Resource Types
# --------------------------------------------------------------------------------
class DoctorType(StrEnum):
    ER = auto()
    SURGEON = auto()
    RADIOLOGIST = auto()


class ScannerType(StrEnum):
    XRAY = auto()
    CT = auto()
    MRI = auto()


class BedType(StrEnum):
    GENERAL = auto()
    ER = auto()


class NurseType(StrEnum):
    GENERAL = auto()
    ER = auto()
    OR = auto()

class OperationType(StrEnum):
    APENDECTOMY = auto()
    C_SECTION = auto()
    DEBRIDEMENT = auto()
    LAPAROTOMY = auto()
    CABG = auto()
    @property
    def base_duration_hours(self) -> float:
        return {
            OperationType.APENDECTOMY: 1.0,
            OperationType.C_SECTION: 1.0,
            OperationType.DEBRIDEMENT: 2.0,
            OperationType.LAPAROTOMY: 4.0,
            OperationType.CABG: 5.0,
        }[self]
        
    @property
    def likelihood(self) -> float:
        return {
            OperationType.APENDECTOMY: 8.0,
            OperationType.C_SECTION: 30.0,
            OperationType.DEBRIDEMENT: 6.5,
            OperationType.LAPAROTOMY: 1.5,
            OperationType.CABG: 1.5,
        }[self]
    
class Severity(StrEnum):
    LOW = auto()
    MEDIUM = auto()  # ie, the value of auto() will be "medium"
    HIGH = auto()
    CRITICAL = auto()

    @property
    def required_doctor(self) -> DoctorType:
        return {
            Severity.LOW: DoctorType.ER,
            Severity.MEDIUM: DoctorType.ER,
            Severity.HIGH: DoctorType.SURGEON,
            Severity.CRITICAL: DoctorType.SURGEON,
        }[self]

    @property
    def required_nurse(self) -> NurseType:
        return {
            Severity.LOW: NurseType.GENERAL,
            Severity.MEDIUM: NurseType.GENERAL,
            Severity.HIGH: NurseType.ER,
            Severity.CRITICAL: NurseType.OR,
        }[self]

    @property
    def required_bed(self) -> BedType:
        return BedType.ER if self in (Severity.HIGH, Severity.CRITICAL) else BedType.GENERAL

    @property
    def required_nurses_count(self) -> int:
        return 2 if self in (Severity.HIGH, Severity.CRITICAL) else 1

    @property
    def max_wait_hours(self) -> float:
        return {Severity.LOW: 8.0, Severity.MEDIUM: 6.0, Severity.HIGH: 4.0, Severity.CRITICAL: 2.0}[self]

    @property
    def initial_condition_score(self) -> float:
        return {Severity.LOW: 1.0, Severity.MEDIUM: 2.0, Severity.HIGH: 4.0, Severity.CRITICAL: 6.0}[self]

    @property
    def wait_deterioration(self) -> float:
        return {Severity.LOW: 0.25, Severity.MEDIUM: 0.5, Severity.HIGH: 0.9, Severity.CRITICAL: 1.4}[self]

    @property
    def recovery_rate(self) -> float:
        return {Severity.LOW: 1.2, Severity.MEDIUM: 1.0, Severity.HIGH: 0.8, Severity.CRITICAL: 0.6}[self]

# --------------------------------------------------------------------------------
# The States
# --------------------------------------------------------------------------------
class Patient(State):
    patient_id: str
    arrival_hour: float
    severity: Severity
    condition_score: float = 0.0 # higher score means worse condition
    max_wait_hours: float = 4.0 # kill the patient with consideration of severity
    waited_hours: float = 0

    treatment_started_hour : Optional[float] = None

    required_doctor: DoctorType = DoctorType.ER
    required_nurse_type: NurseType = NurseType.GENERAL
    required_nurses: int = 1
    required_bed_type: BedType = BedType.GENERAL

    required_scanner: Optional[ScannerType] = None
    operation_duration_hours: float = 0

    @property
    def treatment_hours(self) -> int:
        hours = self.severity.base_treatment_hours # TODO: Add this property to severity
        if self.required_scanner is not None:
            hours += 1 # TODO: Fractional Hour Assignments
        if self.operation_duration_hours > 0:
            hours += self.operation_duration_hours
        return max(1, hours)

class DoctorResource(State):
    resource_id: str
    resource_type: DoctorType
    busy_until_hour: float = 0

class NurseResource(State):
    resource_id: str
    resource_type: NurseType
    busy_until_hour: float = 0

class ScannerResource(State):
    resource_id: str
    resource_type: ScannerType
    busy_until_hour: float = 0

class BedResource(State):
    resource_id: str
    resource_type: BedType
    occupied_by_patient_id: Optional[str] = None

class OperatingRoomResource(State):
    room_id: str
    busy_until_hour: float = 0

class HospitalMetrics(State):
    treated_patients: int = 0
    discharged_patients: int = 0
    deceased_patients: int = 0
    total_wait_time_hours: float = 0

class HospitalState(State):
    episode_id: str
    current_hour: float = 0
    horizon_hours: float = 24

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
    hour: float
    waiting_patients: int
    critical_waiting_patients: int
    resources_free: Dict[str, int]
    queue_by_severity: Dict[str, int]