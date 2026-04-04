from openenv.core.env_server import Environment

import random
import uuid
from typing import List, Dict, Optional

from models import (HospitalState, HospitalObservation, DoctorResource,
                     DoctorType, NurseResource, NurseType, OperationType, ScannerResource, ScannerType,
                     BedResource, BedType, OperatingRoomResource, Severity, Patient,
                     TIME_QUANTA_PER_HOUR,
                     HospitalAction, HospitalMetrics)

class HospitalEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        self._rng = random.Random()
        self._state = HospitalState()
        self._scheduled_arrivals: Dict[int, List[Patient]] = {}
        self._next_patient_index = 0

    # noinspection PyUnusedLocal
    def reset(self, config: dict, seed = None, episode_id = None, **kwargs) -> HospitalObservation:
        # config = {"doctors": {"er": 3, "surgeon": 2}, "nurses": {...}, ..., "patient: {"count": 20, "severity_weights": {"low": 2, "critical": 4}}"}
        # TODO: a default fallback config
        if seed is not None:
            self._rng.seed(seed)

        self._state = HospitalState(
            episode_id = episode_id or str(uuid.uuid4()),

            doctors = self._build_resources(config["doctors"], DoctorResource, DoctorType, "doc"),
            nurses = self._build_resources(config["nurses"], NurseResource, NurseType, "nurse"),
            scanners = self._build_resources(config["scanners"], ScannerResource, ScannerType, "scan"),
            beds = self._build_resources(config["beds"], BedResource, BedType, "bed"),
            operating_rooms = self._build_operating_rooms(config["operating-rooms"])
        )

        self._scheduled_arrivals = self._build_patients_schedule(config["patients"])
        self._next_patient_index = 0
        self._move_to_waiting(hour = 0)
        self._state.metrics = HospitalMetrics()
        return self._observation(message="Started Hospital Shift")
        
    @staticmethod
    def _build_resources(config: dict, resource_class, type_enum, prefix: str) -> list:
        resources = []
        for type_str, count in config.items():
            for i in range(1, count + 1):
                resources.append(resource_class(
                    resource_id=f"{prefix}-{type_str}-{i}",
                    resource_type=type_enum(type_str.upper())
                ))
        return resources
    
    @staticmethod
    def _build_operating_rooms(config: int) -> List[OperatingRoomResource]:
        operating_rooms = []
        for i in range(1, config + 1):
            operating_rooms.append(OperatingRoomResource(
                room_id=f"or-{i}" # or-3
            ))
        return operating_rooms
    
    def _build_patients_schedule(self, config: dict) -> Dict[int, List[Patient]]:
        schedule: Dict[int, List[Patient]] = {slot: [] for slot in range(self._state.horizon_hours)}
        
        count = config["count"]
        spread = config["arrival_spread"]
        weights_raw = config["severity_weights"]
        
        severities = [Severity(k.upper()) for k in weights_raw.keys()]
        severity_weights = list(weights_raw.values())

        for i in range(count):
            # pick arrival time slot based on spread
            if spread == "uniform":
                # pick a random 15-minute slot across the day
                arrival_hour = self._rng.randint(0, self._state.horizon_hours - 1)
            elif spread == "peak_hours":
                # assign a weight of 3 to all peak hours and 1 elsewhere
                arrival_hour = self._rng.choices(
                    range(self._state.horizon_hours),
                    weights = [
                        3 if (slot // self._state.time_quanta_per_hour) in (8, 9, 10, 17, 18, 19) else 1
                        for slot in range(self._state.horizon_hours)
                    ],
                    k = 1
                )[0]
            elif spread == "front_loaded":
                # weight for hour 0 is 24 and decreases through the day
                arrival_hour = self._rng.choices(
                    range(self._state.horizon_hours),
                    weights = [
                        (24 - (slot // self._state.time_quanta_per_hour))
                        for slot in range(self._state.horizon_hours)
                    ],
                    k = 1
                )[0]
            elif spread == "back_loaded":
                # reverse of front_loaded
                arrival_hour = self._rng.choices(
                    range(self._state.horizon_hours),
                    weights = [
                        ((slot // self._state.time_quanta_per_hour) + 1)
                        for slot in range(self._state.horizon_hours)
                    ],
                    k = 1
                )[0]
            elif spread == "custom":
                # supports either 24 hourly weights or per-slot weights
                arrival_weights = config["arrival_weights"]
                if len(arrival_weights) == 24:
                    slot_weights = [arrival_weights[slot // self._state.time_quanta_per_hour] for slot in range(self._state.horizon_hours)]
                elif len(arrival_weights) == self._state.horizon_hours:
                    slot_weights = arrival_weights
                else:
                    raise ValueError("arrival_weights must have length 24 or horizon_hours")

                arrival_hour = self._rng.choices(
                    range(self._state.horizon_hours),
                    weights = slot_weights,
                    k = 1
                )[0]
            else:
                # default to uniform
                arrival_hour = self._rng.randint(0, self._state.horizon_hours - 1)

            severity = self._rng.choices(severities, weights = severity_weights, k = 1)[0]
            # k = 1 => pick 1 element (returns single element list) thus pick the first element from that list

            required_scanner = self._rng.choice([None, ScannerType.XRAY, ScannerType.CT, ScannerType.MRI])
            
            operation_type = None
            operation_duration_hours = 0
            required_blood_units = 0
            required_oxygen = False

            if self._rng.random() < severity.operation_probability:
                operation_choices = list(OperationType)
                weights = [op.likelihood for op in operation_choices]
                operation_type = self._rng.choices(operation_choices, weights=weights, k=1)[0]
                operation_duration_hours = operation_type.base_duration_hours

            if self._rng.random() < severity.oxygen_probability:
                required_oxygen = True

            if self._rng.random() < severity.blood_probability:
                if severity == Severity.MEDIUM:
                    required_blood_units = 1
                elif severity == Severity.HIGH:
                    required_blood_units = self._rng.randint(1, 2)
                else:
                    required_blood_units = self._rng.randint(2, 4)
                    
            patient = Patient(
                patient_id = f"patient-{i + 1}",
                arrival_hour = arrival_hour,
                severity = severity,
                condition_score = severity.initial_condition_score,
                max_wait_hours = severity.max_wait_hours,
                waited_hours = 0,
                required_doctor = operation_type.required_surgeon if operation_type else severity.required_doctor,
                required_nurse_type = severity.required_nurse,
                required_nurses = severity.required_nurses_count,
                required_bed_type = severity.required_bed,
                required_scanner = required_scanner,
                operation_type = operation_type,
                operation_duration_hours = operation_duration_hours,
                required_blood_units = required_blood_units,
                required_oxygen = required_oxygen,
            )
            schedule[arrival_hour].append(patient)

        return schedule

    def _move_to_waiting(self, hour: int) -> None:
        new_patients = self._scheduled_arrivals.get(hour, [])
        if new_patients:
            self._state.waiting_patients.extend(new_patients)
            self._next_patient_index += len(new_patients)

    def _resource_free(self, busy_until_hour: int) -> bool:
        return busy_until_hour <= self._state.current_hour

    def _count_free_resources(self, resources: list, type_enum) -> dict:
        result = {}
        for resource_type in type_enum:
            count = 0
            for r in resources:
                if r.resource_type == resource_type and self._resource_free(r.busy_until_hour):
                    count += 1
            result[resource_type.value] = count
        return result
    
    def _count_free_operating_rooms(self) -> int:
        count = 0
        for room in self._state.operating_rooms:
            if self._resource_free(room.busy_until_hour):
                count += 1
        return count

    def _count_waiting_by_severity(self) -> dict:
        result = {}
        for severity in Severity:
            count = 0
            for p in self._state.waiting_patients:
                if p.severity == severity:
                    count += 1
            result[severity.value] = count
        return result

    def _observation(self, done: bool = False, reward: Optional[float] = None, message: str = "") -> HospitalObservation:
        free_resources = {
            "doctors": self._count_free_resources(self._state.doctors, DoctorType),
            "nurses": self._count_free_resources(self._state.nurses, NurseType),
            "scanners": self._count_free_resources(self._state.scanners, ScannerType),
            "beds": self._count_free_resources(self._state.beds, BedType),
            "operating_rooms": self._count_free_operating_rooms(),
        }

        queue_by_severity = self._count_waiting_by_severity()

        return HospitalObservation(
            done = done,
            reward = reward,
            hour = self._state.current_hour,
            waiting_patients = len(self._state.waiting_patients),
            critical_waiting_patients = queue_by_severity[Severity.CRITICAL.value],
            resources_free = free_resources,
            queue_by_severity = queue_by_severity,
            message = message,
        )
    
    @staticmethod
    def _find_patient(patients: List[Patient], patient_id: str) -> Optional[Patient]:
        for patient in patients:
            if patient.patient_id == patient_id:
                return patient
        return None
    
    def _take_resource(self, resource_ids: List[str | None], resources: List[DoctorResource | ScannerResource], required_type) -> Optional[object]:
        for resource_id in resource_ids:
            resource = next((r for r in resources if r.resource_id == resource_id), None)
            if resource and resource.resource_type == required_type and self._resource_free(resource.busy_until_hour):
                return resource
        return None

    def _take_resources(self, resource_ids: List[str], resources: List[NurseResource], required_type, required_count: int) -> list:
        taken = []
        for resource_id in resource_ids:
            resource = next((r for r in resources if r.resource_id == resource_id), None)
            if resource and resource.resource_type == required_type and self._resource_free(resource.busy_until_hour):
                taken.append(resource)
            if len(taken) >= required_count:
                break
        return taken
    
    def _take_bed(self, bed_id: Optional[str], required_type: BedType) -> Optional[BedResource]:
        if not bed_id:
            return None
        bed = next((b for b in self._state.beds if b.resource_id == bed_id), None)
        if bed and bed.resource_type == required_type and bed.occupied_by_patient_id is None:
            return bed
        return None
    
    def _take_operating_room(self, room_id: Optional[str]) -> Optional[OperatingRoomResource]:
        if not room_id:
            return None
        room = next((r for r in self._state.operating_rooms if r.room_id == room_id), None)
        if room and self._resource_free(room.busy_until_hour):
            return room
        return None

    def _apply_assignments(self, action: HospitalAction) -> None:
        for assignment in action.assignments:
            patient = self._find_patient(self._state.waiting_patients, assignment.patient_id)
            if patient is None:
                continue

            doctor = self._take_resource(assignment.doctor_ids, self._state.doctors, patient.required_doctor)
            nurses = self._take_resources(assignment.nurse_ids, self._state.nurses, patient.required_nurse_type, patient.required_nurses)
            bed = self._take_bed(assignment.bed_id, patient.required_bed_type)
            scanner = self._take_resource([assignment.scanner_id], self._state.scanners, patient.required_scanner) if patient.required_scanner else None
            operating_room = self._take_operating_room(assignment.operating_room_id) if patient.operation_duration_hours > 0 else None
            
            # if resources not in required amount skip assignment
            if doctor is None or len(nurses) < patient.required_nurses or bed is None:
                continue
            if patient.required_scanner is not None and scanner is None:
                continue
            if patient.operation_duration_hours > 0 and operating_room is None:
                continue

            self._state.waiting_patients.remove(patient)
            self._state.active_patients.append(patient)

            patient.treatment_started_hour = self._state.current_hour
            doctor.busy_until_hour = self._state.current_hour + patient.treatment_hours
            for nurse in nurses:
                nurse.busy_until_hour = self._state.current_hour + patient.treatment_hours
            if patient.severity == Severity.CRITICAL:
                bed.occupied_by_patient_id = patient.patient_id
                bed.resource_type = BedType.ER
            elif patient.severity == Severity.HIGH:
                bed.occupied_by_patient_id = patient.patient_id
                bed.resource_type = BedType.GENERAL
            
            if scanner is not None:
                scanner.busy_until_hour = self._state.current_hour + 1
            if operating_room is not None:
                operating_room.busy_until_hour = self._state.current_hour + int(patient.operation_duration_hours)

            self._state.metrics.treated_patients += 1

    def _release_patient_resources(self, patient_id: str) -> None:
        for bed in self._state.beds:
            if bed.occupied_by_patient_id == patient_id:
                bed.occupied_by_patient_id = None

    @staticmethod
    def _patient_died(patient: Patient) -> bool:
        wait_limit = patient.severity.max_wait_hours
        critical_limit = 8.0
        if patient.severity == Severity.CRITICAL:
            return patient.waited_hours > wait_limit or patient.condition_score >= critical_limit
        return False
    
    @staticmethod
    def _update_severity(patient: Patient) -> None:
        if patient.severity == Severity.HIGH and patient.waited_hours >= patient.severity.max_wait_hours:
            patient.severity = Severity.CRITICAL


    def _advance_waiting_patients(self) -> None:
        surviving_waiting: List[Patient] = []
        for patient in self._state.waiting_patients:
            patient.waited_hours += 1
            patient.condition_score += patient.severity.wait_deterioration / TIME_QUANTA_PER_HOUR
            self._update_severity(patient)
            self._state.metrics.total_wait_time_hours += 1

            if self._patient_died(patient):
                self._state.deceased_patients.append(patient)
            else:
                surviving_waiting.append(patient)
        self._state.waiting_patients = surviving_waiting

    def _advance_active_patients(self) -> int:
        remaining_active: List[Patient] = []
        discharges = 0

        for patient in self._state.active_patients:
            hours_elapsed = self._state.current_hour - patient.treatment_started_hour
            patient.condition_score = max(0.0, patient.condition_score - (patient.severity.recovery_rate / TIME_QUANTA_PER_HOUR))

            if hours_elapsed >= patient.treatment_hours:
                patient.is_stable = True
                self._state.discharged_patients.append(patient)
                discharges += 1
                self._release_patient_resources(patient.patient_id)
            elif self._patient_died(patient):
                self._state.deceased_patients.append(patient)
                self._release_patient_resources(patient.patient_id)
            else:
                remaining_active.append(patient)

        self._state.active_patients = remaining_active
        self._state.metrics.discharged_patients += discharges
        self._state.metrics.deceased_patients = len(self._state.deceased_patients)
        return discharges

    def _release_resources(self, current_hour: int) -> None:
        for doctor in self._state.doctors:
            if doctor.busy_until_hour <= current_hour:
                doctor.busy_until_hour = 0
        for nurse in self._state.nurses:
            if nurse.busy_until_hour <= current_hour:
                nurse.busy_until_hour = 0
        for scanner in self._state.scanners:
            if scanner.busy_until_hour <= current_hour:
                scanner.busy_until_hour = 0
        for room in self._state.operating_rooms:
            if room.busy_until_hour <= current_hour:
                room.busy_until_hour = 0
    
    @staticmethod
    def _status_message(discharges: int, deaths: int, done: bool) -> str:
        if done:
            return "Shift complete."
        parts = []
        if discharges:
            parts.append(f"{discharges} patients discharged")
        if deaths:
            parts.append(f"{deaths} patients died")
        if not parts:
            parts.append("No major changes this hour")
        return ", ".join(parts)


    def _flatten_arrivals(self) -> List[Patient]:
        arrivals: List[Patient] = []
        for hour in range(self._state.horizon_hours):
            arrivals.extend(self._scheduled_arrivals.get(hour, []))
        return arrivals

    # noinspection PyUnusedLocal
    def step(self, action: HospitalAction, **kwargs) -> HospitalObservation:
        current_hour = self._state.current_hour
        before_deceased = len(self._state.deceased_patients)
        before_discharged = len(self._state.discharged_patients)
        before_wait_time = self._state.metrics.total_wait_time_hours

        self._move_to_waiting(current_hour)
        self._apply_assignments(action)

        self._advance_waiting_patients()
        self._advance_active_patients()

        self._state.current_hour += 1
        self._release_resources(self._state.current_hour)

        deaths_this_step = len(self._state.deceased_patients) - before_deceased
        discharges_this_step = len(self._state.discharged_patients) - before_discharged
        wait_penalty = self._state.metrics.total_wait_time_hours - before_wait_time

        all_patients_arrived = self._next_patient_index >= len(self._flatten_arrivals())
        done = self._state.current_hour >= self._state.horizon_hours or (
            not self._state.waiting_patients and
            not self._state.active_patients and
            all_patients_arrived
        )

        reward = discharges_this_step * 1.0 - deaths_this_step * 2.0 - 0.1 * (wait_penalty / TIME_QUANTA_PER_HOUR)
        self._state.metrics.objective_score += reward

        return self._observation(done=done, reward=reward, message=self._status_message(discharges_this_step, deaths_this_step, done))


    @property
    def state(self) -> HospitalState:
        return self._state
