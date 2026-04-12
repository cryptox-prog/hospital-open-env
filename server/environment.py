from openenv.core.env_server import Environment

import random
import uuid
from typing import List, Dict, Optional

from models import (HospitalState, HospitalObservation, DoctorResource,
                     DoctorType, NurseResource, NurseType, OperationType, ScannerResource, ScannerType,
                     BedResource, BedType, OperatingRoomResource, Severity, Patient,
                     HospitalAction, HospitalMetrics, CRITICAL_LIMIT, hours_from_quanta)

DEFAULT_RESET_CONFIG = {
    "doctors": {
        "general": 4,
        "er": 3,
        "radiologist": 2,
        "general_surgeon": 2,
        "cardiothoracic_surgeon": 2,
        "obstetric_surgeon": 1,
    },
    "nurses": {
        "general": 8,
        "er": 6,
        "or": 3,
    },
    "scanners": {
        "xray": 2,
        "ct": 1,
        "mri": 1,
    },
    "beds": {
        "general": 16,
        "er": 6,
    },
    "operating-rooms": 3,
    "patients": {
        "count": 36,
        "arrival_spread": "front_loaded",
        "severity_weights": {"low": 35, "medium": 35, "high": 20, "critical": 10},
    },
}

class HospitalEnvironment(Environment):
    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self):
        self._rng = random.Random()
        self._state = HospitalState(
            episode_id=str(uuid.uuid4()),
            doctors=[],
            nurses=[],
            scanners=[],
            beds=[],
            operating_rooms=[],
        )
        self._scheduled_arrivals: Dict[int, List[Patient]] = {}
        self._arrivals_moved_quanta: set[int] = set()
        self._next_patient_index = 0

    # noinspection PyUnusedLocal
    def reset(self, seed=None, episode_id=None, config: Optional[dict] = None, **kwargs) -> HospitalObservation:
        # config = {"doctors": {"er": 3, "surgeon": 2}, "nurses": {...}, ..., "patient: {"count": 20, "severity_weights": {"low": 2, "critical": 4}}"}
        if seed is not None:
            self._rng.seed(seed)

        effective_config = self._resolve_config(config)

        self._state = HospitalState(
            episode_id = episode_id or str(uuid.uuid4()),

            doctors = self._build_resources(effective_config["doctors"], DoctorResource, DoctorType, "doc"),
            nurses = self._build_resources(effective_config["nurses"], NurseResource, NurseType, "nurse"),
            scanners = self._build_resources(effective_config["scanners"], ScannerResource, ScannerType, "scan"),
            beds = self._build_resources(effective_config["beds"], BedResource, BedType, "bed"),
            operating_rooms = self._build_operating_rooms(effective_config["operating-rooms"])
        )

        self._scheduled_arrivals = self._build_patients_schedule(effective_config["patients"])
        self._arrivals_moved_quanta = set()
        self._next_patient_index = 0
        self._move_to_waiting(quantum = 0)
        self._state.metrics = HospitalMetrics()
        return self._observation(message="Started Hospital Shift")

    @staticmethod
    def _resolve_config(config: Optional[dict]) -> dict:
        if not config:
            return DEFAULT_RESET_CONFIG

        merged_config = dict(DEFAULT_RESET_CONFIG)
        for key, value in config.items():
            if isinstance(value, dict) and isinstance(merged_config.get(key), dict):
                nested = dict(merged_config[key])
                nested.update(value)
                merged_config[key] = nested
            else:
                merged_config[key] = value
        return merged_config
        
    @staticmethod
    def _build_resources(config: dict, resource_class, type_enum, prefix: str) -> list:
        resources = []
        for type_str, count in config.items():
            for i in range(1, count + 1):
                resources.append(resource_class(
                    resource_id=f"{prefix}-{type_str}-{i}",
                    resource_type=type_enum(type_str.lower())
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
        schedule: Dict[int, List[Patient]] = {quantum: [] for quantum in range(0, self._state.horizon_quanta, self._state.quanta_per_step)}
        
        count = config["count"]
        spread = config["arrival_spread"]
        weights_raw = config["severity_weights"]
        
        severities = [Severity(k.lower()) for k in weights_raw.keys()]
        severity_weights = list(weights_raw.values())

        arrival_cutoff_quantum = 20 * self._state.time_quanta_per_hour
        arrival_quanta = [
            quantum
            for quantum in range(0, self._state.horizon_quanta, self._state.quanta_per_step)
            if quantum < arrival_cutoff_quantum
        ]
        if not arrival_quanta:
            raise ValueError("quanta_per_step is too large for the configured horizon")

        for i in range(count):
            # pick arrival quantum based on spread
            if spread == "uniform":
                # pick a random step-aligned quantum across the day
                arrival_quantum = self._rng.choice(arrival_quanta)
            elif spread == "peak_hours":
                # assign a weight of 3 to all peak hours and 1 elsewhere
                arrival_quantum = self._rng.choices(
                    arrival_quanta,
                    weights = [
                        3 if (quantum // self._state.time_quanta_per_hour) in (4, 8, 12, 16) else 1
                        for quantum in arrival_quanta
                    ],
                    k = 1
                )[0]
            elif spread == "front_loaded":
                # weight for hour 0 is 24 and decreases through the day
                arrival_quantum = self._rng.choices(
                    arrival_quanta,
                    weights = [
                        (24 - (quantum // self._state.time_quanta_per_hour))
                        for quantum in arrival_quanta
                    ],
                    k = 1
                )[0]
            elif spread == "back_loaded":
                # reverse of front_loaded
                arrival_quantum = self._rng.choices(
                    arrival_quanta,
                    weights = [
                        ((quantum // self._state.time_quanta_per_hour) + 1)
                        for quantum in arrival_quanta
                    ],
                    k = 1
                )[0]
            elif spread == "custom":
                arrival_weights = config["arrival_weights"]

                if len(arrival_weights) != len(arrival_quanta):
                    raise ValueError(
                        f"arrival_weights must have length {len(arrival_quanta)} "
                        f"(got {len(arrival_weights)})"
                    )

                arrival_quantum = self._rng.choices(
                    arrival_quanta,
                    weights=arrival_weights,
                    k=1
                )[0]
            else:
                # default to uniform over step-aligned quanta
                arrival_quantum = self._rng.choice(arrival_quanta)

            severity = self._rng.choices(severities, weights = severity_weights, k = 1)[0]
            # k = 1 => pick 1 element (returns single element list) thus pick the first element from that list

            required_scanner = None
            if self._rng.random() < severity.scanner_probability:
                required_scanner = self._rng.choice([ScannerType.XRAY, ScannerType.CT, ScannerType.MRI])
            
            operation_type = None
            operation_duration_quanta = 0
            required_blood_units = 0
            required_oxygen = False

            if self._rng.random() < severity.operation_probability:
                operation_choices = list(OperationType)
                weights = [op.likelihood for op in operation_choices]
                operation_type = self._rng.choices(operation_choices, weights=weights, k=1)[0]
                operation_duration_quanta = operation_type.base_duration_quanta


            if self._rng.random() < severity.oxygen_probability:
                required_oxygen = True

            if self._rng.random() < severity.blood_probability:
                if severity == Severity.MEDIUM:
                    required_blood_units = 1
                elif severity == Severity.HIGH:
                    required_blood_units = self._rng.randint(1, 2)
                else:
                    required_blood_units = self._rng.randint(2, 4)

            required_nurse_type = severity.required_nurse
            required_nurses = severity.required_nurses_count
            if operation_type:
                required_nurse_type = NurseType.OR
                required_nurses = 1
                    
            patient = Patient(
                patient_id = f"patient-{i + 1}",
                arrival_quantum = arrival_quantum,
                severity = severity,
                condition_score = severity.initial_condition_score,
                max_wait_quanta = severity.max_wait_quanta(self._rng),
                waited_quanta = 0,
                required_doctor = operation_type.required_surgeon if operation_type else severity.required_doctor,
                required_nurse_type = required_nurse_type,
                required_nurses = required_nurses,
                required_bed_type = severity.required_bed,
                required_scanner = required_scanner,
                operation_type = operation_type,
                operation_duration_quanta = operation_duration_quanta,
                required_blood_units = required_blood_units,
                required_oxygen = required_oxygen,
            )
            schedule[arrival_quantum].append(patient)

        return schedule

    def _move_to_waiting(self, quantum: int) -> None:
        if quantum in self._arrivals_moved_quanta:
            return

        new_patients = self._scheduled_arrivals.get(quantum, [])
        arrived = []
        overflowed = []
        if new_patients:
            current_total = len(self._state.waiting_patients) + len(self._state.active_patients)
            for patient in new_patients:
                if current_total < self._state.max_total_capacity:
                    self._state.waiting_patients.append(patient)
                    arrived.append(patient)
                    current_total += 1
                else:
                    self._state.overflow_patients.append(patient)
                    overflowed.append(patient)
                    self._state.metrics.overflow_patients += 1
            self._next_patient_index += len(new_patients)

        self._arrivals_moved_quanta.add(quantum)

    def _resource_free(self, busy_until_quantum: int) -> bool:
        return busy_until_quantum <= self._state.current_quantum

    def _count_free_resources(self, resources: list, type_enum) -> dict:
        result = {}
        for resource_type in type_enum:
            count = 0
            for r in resources:
                if r.resource_type != resource_type:
                    continue
                if self._resource_free(r.busy_until_quantum):
                    count += 1
            result[resource_type.value] = count
        return result
    
    def _count_free_operating_rooms(self) -> int:
        count = 0
        for room in self._state.operating_rooms:
            if self._resource_free(room.busy_until_quantum):
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

    def _deterioration_per_hour_to_deterioration_per_quanta(self, deterioration_per_hour: float) -> float:
        return deterioration_per_hour / self._state.time_quanta_per_hour
    
    def _severity_wait_penalty(self) -> float:
        penalty = 0.0
        for patient in self._state.waiting_patients:
            hours_waited = hours_from_quanta(patient.waited_quanta)
            if patient.severity == Severity.CRITICAL:
                penalty += 0.05 * hours_waited
            elif patient.severity == Severity.HIGH:
                penalty += 0.03 * hours_waited
            elif patient.severity == Severity.MEDIUM:
                penalty += 0.015 * hours_waited
            else:
                penalty += 0.005 * hours_waited
        return penalty

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
            current_quantum = self._state.current_quantum,
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

    @staticmethod
    def _find_by_id(items: list, id_attr: str, target_id: Optional[str]) -> Optional[object]:
        if not target_id:
            return None
        for item in items:
            if getattr(item, id_attr, None) == target_id:
                return item
        return None
    
    def _take_matching_resources(self, resource_ids: List[Optional[str]], resources: List[DoctorResource | NurseResource | ScannerResource | BedResource], required_type, required_count: int = 1) -> list:
        matched_resources = []
        seen_resource_ids = set()
        for resource_id in resource_ids:
            if not resource_id or resource_id in seen_resource_ids:
                continue
            resource = self._find_by_id(resources, "resource_id", resource_id)
            if resource and resource.resource_type == required_type and self._resource_free(resource.busy_until_quantum):
                matched_resources.append(resource)
                seen_resource_ids.add(resource_id)
            if len(matched_resources) >= required_count:
                break
        return matched_resources
    
    def _take_operating_room(self, room_id: Optional[str]) -> Optional[OperatingRoomResource]:
        room = self._find_by_id(self._state.operating_rooms, "room_id", room_id)
        if room and self._resource_free(room.busy_until_quantum):
            return room
        return None

    def _apply_assignments(self, action: HospitalAction) -> None:
        for assignment in action.assignments:
            patient = self._find_patient(self._state.waiting_patients, assignment.patient_id)
            if patient is None:
                continue

            doctor_matches = self._take_matching_resources(assignment.doctor_ids, self._state.doctors, patient.required_doctor)
            doctor = doctor_matches[0] if doctor_matches else None
            nurses = self._take_matching_resources(assignment.nurse_ids, self._state.nurses, patient.required_nurse_type, patient.required_nurses)
            bed_matches = self._take_matching_resources([assignment.bed_id], self._state.beds, patient.required_bed_type)
            bed = bed_matches[0] if bed_matches else None
            scanner_matches = self._take_matching_resources([assignment.scanner_id], self._state.scanners, patient.required_scanner) if patient.required_scanner else []
            scanner = scanner_matches[0] if scanner_matches else None
            operating_room = self._take_operating_room(assignment.operating_room_id) if patient.operation_duration_quanta > 0 else None
            
            # if resources not in required amount skip assignment
            if doctor is None or len(nurses) < patient.required_nurses or bed is None:
                continue
            if patient.required_scanner is not None and scanner is None:
                continue
            if patient.operation_duration_quanta > 0 and operating_room is None:
                continue
            
            # TODO: maybe put this in _advance_waiting
            self._state.waiting_patients.remove(patient)
            self._state.active_patients.append(patient)
            self._state.metrics.active_patients += 1

            if patient.severity == Severity.CRITICAL:
                self._state.metrics.active_critical_patients += 1
            elif patient.severity == Severity.HIGH:
                self._state.metrics.active_high_patients += 1
            elif patient.severity == Severity.MEDIUM:
                self._state.metrics.active_medium_patients += 1
            elif patient.severity == Severity.LOW:
                self._state.metrics.active_low_patients += 1

            patient.treatment_started_quantum = self._state.current_quantum
            doctor.busy_until_quantum = self._state.current_quantum + patient.treatment_quanta
            for nurse in nurses:
                nurse.busy_until_quantum = self._state.current_quantum + patient.treatment_quanta
            bed.busy_until_quantum = self._state.current_quantum + patient.treatment_quanta
            
            if scanner is not None:
                scanner.busy_until_quantum = self._state.current_quantum + 1
            if operating_room is not None:
                operating_room.busy_until_quantum = self._state.current_quantum + int(patient.operation_duration_quanta)

            self._state.metrics.treated_patients += 1

    @staticmethod
    def _patient_died(patient: Patient) -> bool:
        wait_limit = patient.max_wait_quanta
        critical_limit = CRITICAL_LIMIT
        if patient.severity == Severity.CRITICAL:
            return patient.waited_quanta > wait_limit or patient.condition_score >= critical_limit
        return False
    
    @staticmethod
    def _patient_left(patient: Patient) -> bool:
        if patient.severity in (Severity.LOW, Severity.MEDIUM):
            return patient.waited_quanta >= patient.max_wait_quanta
        return False

    def _update_severity(self, patient: Patient) -> None:
        if patient.severity == Severity.HIGH and patient.waited_quanta >= patient.max_wait_quanta:
            patient.severity = Severity.CRITICAL
            patient.max_wait_quanta += patient.severity.max_wait_quanta(self._rng)
            patient.required_doctor = patient.severity.required_doctor
            patient.required_nurse_type = patient.severity.required_nurse
            patient.required_nurses = patient.severity.required_nurses_count
            patient.required_bed_type = patient.severity.required_bed


    def _advance_waiting_patients(self) -> None:
        surviving_waiting: List[Patient] = []
        for patient in self._state.waiting_patients:
            patient.waited_quanta += 1
            patient.condition_score += self._deterioration_per_hour_to_deterioration_per_quanta(patient.severity.wait_deterioration)
            self._update_severity(patient)

            if self._patient_died(patient):
                self._state.deceased_patients.append(patient)
                self._state.metrics.deceased_patients += 1
            elif self._patient_left(patient):
                self._state.left_patients.append(patient)
                self._state.metrics.left_patients += 1
            else:
                surviving_waiting.append(patient)
        self._state.waiting_patients = surviving_waiting

    def _advance_active_patients(self) -> None:
        remaining_active: List[Patient] = []

        for patient in self._state.active_patients:
            quanta_elapsed = self._state.current_quantum - patient.treatment_started_quantum
            # TODO: Look into condition score logic, maybe remove this
            patient.condition_score = max(0.0, patient.condition_score - self._deterioration_per_hour_to_deterioration_per_quanta(patient.severity.recovery_rate))

            if quanta_elapsed >= patient.treatment_quanta:
                patient.is_stable = True
                self._state.metrics.active_patients -= 1
                self._state.discharged_patients.append(patient)
                if patient.severity == Severity.CRITICAL:
                    self._state.metrics.discharged_critical += 1
                    self._state.metrics.active_critical_patients -= 1
                elif patient.severity == Severity.HIGH:
                    self._state.metrics.discharged_high += 1
                    self._state.metrics.active_high_patients -= 1
                elif patient.severity == Severity.MEDIUM:
                    self._state.metrics.discharged_med += 1
                    self._state.metrics.active_medium_patients -= 1
                elif patient.severity == Severity.LOW:
                    self._state.metrics.discharged_low += 1
                    self._state.metrics.active_low_patients -= 1
            # TODO: seems redundant, as patients don't die during treatment
            elif self._patient_died(patient):
                self._state.deceased_patients.append(patient)
                self._state.metrics.deceased_patients += 1
            else:
                remaining_active.append(patient)

        self._state.active_patients = remaining_active

    def _release_resources(self, current_quantum: int) -> None:
        for bed in self._state.beds:
            if bed.busy_until_quantum <= current_quantum:
                bed.busy_until_quantum = 0
        for doctor in self._state.doctors:
            if doctor.busy_until_quantum <= current_quantum:
                doctor.busy_until_quantum = 0
        for nurse in self._state.nurses:
            if nurse.busy_until_quantum <= current_quantum:
                nurse.busy_until_quantum = 0
        for scanner in self._state.scanners:
            if scanner.busy_until_quantum <= current_quantum:
                scanner.busy_until_quantum = 0
        for room in self._state.operating_rooms:
            if room.busy_until_quantum <= current_quantum:
                room.busy_until_quantum = 0
    
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
            parts.append("No major changes this quantum")
        return ", ".join(parts)


    def _flatten_arrivals(self) -> List[Patient]:
        arrivals: List[Patient] = []
        for quantum in range(0, self._state.horizon_quanta, self._state.quanta_per_step):
            arrivals.extend(self._scheduled_arrivals.get(quantum, []))
        return arrivals

    # noinspection PyUnusedLocal
    def step(self, action: HospitalAction, *args, **kwargs) -> HospitalObservation:
        current_quantum = self._state.current_quantum
        before_deceased = self._state.metrics.deceased_patients
        before_active_critical = self._state.metrics.active_critical_patients
        before_active_high = self._state.metrics.active_high_patients
        before_active_med = self._state.metrics.active_medium_patients
        before_active_low = self._state.metrics.active_low_patients
        before_left = self._state.metrics.left_patients
        before_denied_admission = self._state.metrics.overflow_patients
        before_discharged_critical = self._state.metrics.discharged_critical
        before_discharged_high = self._state.metrics.discharged_high
        before_discharged_med = self._state.metrics.discharged_med
        before_discharged_low = self._state.metrics.discharged_low

        quanta_to_advance = min(
            self._state.quanta_per_step,
            self._state.horizon_quanta - self._state.current_quantum,
        )

        self._move_to_waiting(current_quantum)
        self._apply_assignments(action)

        for quantum_index in range(quanta_to_advance):
            self._advance_waiting_patients()
            self._advance_active_patients()

            self._state.current_quantum += 1
            self._release_resources(self._state.current_quantum)

            if quantum_index < quanta_to_advance - 1:
                self._move_to_waiting(self._state.current_quantum)

        deaths_this_step = self._state.metrics.deceased_patients - before_deceased
        critical_discharges_this_step = self._state.metrics.discharged_critical - before_discharged_critical
        high_discharges_this_step = self._state.metrics.discharged_high - before_discharged_high
        med_discharges_this_step = self._state.metrics.discharged_med - before_discharged_med
        low_discharges_this_step = self._state.metrics.discharged_low - before_discharged_low
        critical_active_this_step = self._state.metrics.active_critical_patients - before_active_critical + critical_discharges_this_step
        high_active_this_step = self._state.metrics.active_high_patients - before_active_high + high_discharges_this_step
        med_active_this_step = self._state.metrics.active_medium_patients - before_active_med + med_discharges_this_step
        low_active_this_step = self._state.metrics.active_low_patients - before_active_low + low_discharges_this_step
        left_this_step = self._state.metrics.left_patients - before_left
        denied_admission_this_step = self._state.metrics.overflow_patients - before_denied_admission

        total_patients = len(self._flatten_arrivals())
        all_patients_arrived = self._next_patient_index >= total_patients
        done = self._state.current_quantum >= self._state.horizon_quanta or (
            not self._state.waiting_patients and
            not self._state.active_patients and
            all_patients_arrived
        )

        # TODO: Instead of rewarding discharges, reward the start of treatment
        reward = (
            critical_active_this_step * 15
            + high_active_this_step * 9
            + med_active_this_step * 3
            + low_active_this_step * 1
            - deaths_this_step * 25
            - self._severity_wait_penalty() * total_patients
            - denied_admission_this_step * 2
            - left_this_step * 4
        )

        reward = reward * 100 / (total_patients if total_patients > 0 else reward)

        return self._observation(done=done, reward=reward, message=self._status_message(critical_discharges_this_step + high_discharges_this_step + med_discharges_this_step + low_discharges_this_step, deaths_this_step, done))


    @property
    def state(self) -> HospitalState:
        return self._state
