from enum import StrEnum, auto
from typing import Dict, List, Optional

from openenv.core.env_server import Action, Observation, State

TIME_QUANTUM_MINUTES = 15
TIME_QUANTA_PER_HOUR = 60 // TIME_QUANTUM_MINUTES


def quanta_from_hours(hours: int) -> int:
    return hours * TIME_QUANTA_PER_HOUR


def quanta_from_minutes(minutes: int) -> int:
    if minutes % TIME_QUANTUM_MINUTES != 0:
        raise ValueError("minutes must be divisible by TIME_QUANTUM_MINUTES")
    return minutes // TIME_QUANTUM_MINUTES

# --------------------------------------------------------------------------------
# The Resource Types
# --------------------------------------------------------------------------------
class DoctorType(StrEnum):
    GENERAL = auto()
    ER = auto()
    RADIOLOGIST = auto()

    # Surgeon specializations
    GENERAL_SURGEON = auto()
    CARDIOTHORACIC_SURGEON = auto()
    OBSTETRIC_SURGEON = auto()


class ScannerType(StrEnum):
    XRAY = auto()
    CT = auto()
    MRI = auto()


class BedType(StrEnum):
    GENERAL = auto()
    ER = auto()

class BloodType(StrEnum):
    O_POS = auto()
    O_NEG = auto()
    A_POS = auto()
    B_POS = auto()

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
    def base_duration_hours(self) -> int:
        return {
            OperationType.APENDECTOMY: quanta_from_hours(1),
            OperationType.C_SECTION: quanta_from_hours(1),
            OperationType.DEBRIDEMENT: quanta_from_hours(2),
            OperationType.LAPAROTOMY: quanta_from_hours(4),
            OperationType.CABG: quanta_from_hours(5),
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
    
    @property
    def required_surgeon(self) -> DoctorType:
        return {
            OperationType.APENDECTOMY: DoctorType.GENERAL_SURGEON,
            OperationType.C_SECTION: DoctorType.OBSTETRIC_SURGEON,
            OperationType.DEBRIDEMENT: DoctorType.GENERAL_SURGEON,
            OperationType.LAPAROTOMY: DoctorType.GENERAL_SURGEON,
            OperationType.CABG: DoctorType.CARDIOTHORACIC_SURGEON,
        }[self]
    
class Severity(StrEnum):
    LOW = auto()
    MEDIUM = auto()  # ie, the value of auto() will be "medium"
    HIGH = auto()
    CRITICAL = auto()

    @property
    def required_doctor(self) -> DoctorType:
        return {
            Severity.LOW: DoctorType.GENERAL,
            Severity.MEDIUM: DoctorType.GENERAL,
            Severity.HIGH: DoctorType.ER,
            Severity.CRITICAL: DoctorType.ER,
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
    def max_wait_hours(self) -> int:
        return {
            Severity.LOW: quanta_from_hours(4),
            Severity.MEDIUM: quanta_from_hours(3),
            Severity.HIGH: quanta_from_hours(2),
            Severity.CRITICAL: quanta_from_hours(2),
        }[self]

    @property
    def initial_condition_score(self) -> float:
        return {Severity.LOW: 1.0, Severity.MEDIUM: 2.0, Severity.HIGH: 4.0, Severity.CRITICAL: 6.0}[self]

    @property
    def wait_deterioration(self) -> float:
        return {Severity.LOW: 0.25, Severity.MEDIUM: 0.5, Severity.HIGH: 0.9, Severity.CRITICAL: 1.4}[self]

    @property
    def recovery_rate(self) -> float:
        return {Severity.LOW: 1.2, Severity.MEDIUM: 1.0, Severity.HIGH: 0.8, Severity.CRITICAL: 0.6}[self]

    @property
    def operation_probability(self) -> float:
        return {
            Severity.LOW: 0.0,
            Severity.MEDIUM: 0.0,
            Severity.HIGH: 0.35,
            Severity.CRITICAL: 0.90,
        }[self]

    @property
    def oxygen_probability(self) -> float:
        return {
            Severity.LOW: 0.0,
            Severity.MEDIUM: 0.10,
            Severity.HIGH: 0.55,
            Severity.CRITICAL: 0.90,
        }[self]

    @property
    def blood_probability(self) -> float:
        return {
            Severity.LOW: 0.0,
            Severity.MEDIUM: 0.05,
            Severity.HIGH: 0.35,
            Severity.CRITICAL: 0.80,
        }[self]

    @property
    def base_treatment_hours(self) -> int:
        return {
            Severity.LOW: quanta_from_minutes(15),
            Severity.MEDIUM: quanta_from_hours(1),
            Severity.HIGH: quanta_from_hours(2),
            Severity.CRITICAL: quanta_from_hours(3),
        }[self]

# --------------------------------------------------------------------------------
# The States
# --------------------------------------------------------------------------------
class Patient(State):
    patient_id: str
    arrival_hour: int
    severity: Severity
    max_wait_hours: int = 0
    condition_score: float = 0.0 # higher score means worse condition
    waited_hours: int = 0
    
    treatment_started_hour : Optional[int] = None

    required_doctor: DoctorType = DoctorType.ER
    required_nurse_type: NurseType = NurseType.GENERAL
    required_nurses: int = 1
    required_bed_type: BedType = BedType.GENERAL
    required_blood_units: int = 0
    required_oxygen: bool = False
    required_scanner: Optional[ScannerType] = None
    operation_type: Optional[OperationType] = None
    operation_duration_hours: int = 0

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
    busy_until_hour: int = 0

class NurseResource(State):
    resource_id: str
    resource_type: NurseType
    busy_until_hour: int = 0

class ScannerResource(State):
    resource_id: str
    resource_type: ScannerType
    busy_until_hour: int = 0

class BedResource(State):
    resource_id: str
    resource_type: BedType
    occupied_by_patient_id: Optional[str] = None

class BloodResource(State):
    resource_id: str
    resource_type: BloodType
    units_available: int = 0


class OxygenResource(State):
    resource_id: str
    busy_until_hour: int = 0

class OperatingRoomResource(State):
    room_id: str
    busy_until_hour: int = 0

class HospitalMetrics(State):
    treated_patients: int = 0
    discharged_patients: int = 0
    deceased_patients: int = 0
    total_wait_time_hours: int = 0

class HospitalState(State):
    episode_id: str
    current_hour: int = 0
    horizon_hours: int = quanta_from_hours(24)
    time_quantum_minutes: int = TIME_QUANTUM_MINUTES
    time_quanta_per_hour: int = TIME_QUANTA_PER_HOUR

    waiting_patients: List[Patient] = []
    active_patients: List[Patient] = []
    discharged_patients: List[Patient] = []
    deceased_patients: List[Patient] = []

    doctors: List[DoctorResource] = []
    nurses: List[NurseResource] = []
    scanners: List[ScannerResource] = []
    beds: List[BedResource] = []
    operating_rooms: List[OperatingRoomResource] = []
    blood_bank: List[BloodResource] = []
    oxygen_supply: List[OxygenResource] = []
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
    hour: int
    waiting_patients: int
    critical_waiting_patients: int
    resources_free: Dict[str, int]
    queue_by_severity: Dict[str, int]