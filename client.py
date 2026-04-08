from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from models import (
	HospitalAction,
	HospitalObservation,
	HospitalState,
	Patient,
	DoctorResource,
	NurseResource,
	ScannerResource,
	BedResource,
	OperatingRoomResource,
	BloodResource,
	OxygenResource,
	HospitalMetrics,
)


class HospitalEnv(EnvClient[HospitalAction, HospitalObservation, HospitalState]):
	
	def _step_payload(self, action: HospitalAction) -> dict:
	    # Converts HospitalAction to json for web transfer
		return {"assignments": [a.model_dump() for a in action.assignments]}


	def _parse_result(self, payload: dict) -> StepResult:
		# Parses the result from the environment after taking a step
		observation_payload = payload.get("observation", {})
		observation = HospitalObservation(
			done=payload.get("done", False),
			reward=payload.get("reward"),
			current_quantum=observation_payload.get("current_quantum", 0),
			waiting_patients=observation_payload.get("waiting_patients", 0),
			critical_waiting_patients=observation_payload.get("critical_waiting_patients", 0),
			resources_free=observation_payload.get("resources_free", {}),
			queue_by_severity=observation_payload.get("queue_by_severity", {}),
			message=observation_payload.get("message", ""),
		)

		return StepResult(
			observation=observation,
			reward=payload.get("reward"),
			done=payload.get("done", False),
		)

	def _parse_state(self, payload: dict) -> HospitalState:
		# Parses the full state of the hospital environment from the payload
		# Properly deserialize nested objects from JSON
		waiting_patients = [Patient.model_validate(p) for p in payload.get("waiting_patients", [])]
		active_patients = [Patient.model_validate(p) for p in payload.get("active_patients", [])]
		discharged_patients = [Patient.model_validate(p) for p in payload.get("discharged_patients", [])]
		left_patients = [Patient.model_validate(p) for p in payload.get("left_patients", [])]
		overflow_patients = [Patient.model_validate(p) for p in payload.get("overflow_patients", [])]
		deceased_patients = [Patient.model_validate(p) for p in payload.get("deceased_patients", [])]
		
		doctors = [DoctorResource.model_validate(d) for d in payload.get("doctors", [])]
		nurses = [NurseResource.model_validate(n) for n in payload.get("nurses", [])]
		scanners = [ScannerResource.model_validate(s) for s in payload.get("scanners", [])]
		beds = [BedResource.model_validate(b) for b in payload.get("beds", [])]
		operating_rooms = [OperatingRoomResource.model_validate(o) for o in payload.get("operating_rooms", [])]
		blood_bank = [BloodResource.model_validate(b) for b in payload.get("blood_bank", [])]
		oxygen_supply = [OxygenResource.model_validate(o) for o in payload.get("oxygen_supply", [])]
		metrics = HospitalMetrics.model_validate(payload.get("metrics", {}))
		
		return HospitalState(
			episode_id=payload.get("episode_id"),
			current_quantum=payload.get("current_quantum", 0),
			horizon_quanta=payload.get("horizon_quanta", 0),
			time_quantum_minutes=payload.get("time_quantum_minutes", 15),
			time_quanta_per_hour=payload.get("time_quanta_per_hour", 4),
			quanta_per_step=payload.get("quanta_per_step", 2),
			waiting_patients=waiting_patients,
			active_patients=active_patients,
			discharged_patients=discharged_patients,
			left_patients=left_patients,
			overflow_patients=overflow_patients,
			deceased_patients=deceased_patients,
			doctors=doctors,
			nurses=nurses,
			scanners=scanners,
			beds=beds,
			operating_rooms=operating_rooms,
			blood_bank=blood_bank,
			oxygen_supply=oxygen_supply,
			metrics=metrics,
		)
