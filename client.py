from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from models import HospitalAction, HospitalObservation, HospitalState


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
		return HospitalState(
			episode_id=payload.get("episode_id"),
			current_quantum=payload.get("current_quantum", 0),
			horizon_quanta=payload.get("horizon_quanta", 0),
			time_quantum_minutes=payload.get("time_quantum_minutes", 15),
			time_quanta_per_hour=payload.get("time_quanta_per_hour", 4),
			quanta_per_step=payload.get("quanta_per_step", 2),
			waiting_patients=payload.get("waiting_patients", []),
			active_patients=payload.get("active_patients", []),
			discharged_patients=payload.get("discharged_patients", []),
			deceased_patients=payload.get("deceased_patients", []),
			doctors=payload.get("doctors", []),
			nurses=payload.get("nurses", []),
			scanners=payload.get("scanners", []),
			beds=payload.get("beds", []),
			operating_rooms=payload.get("operating_rooms", []),
			blood_bank=payload.get("blood_bank", []),
			oxygen_supply=payload.get("oxygen_supply", []),
			metrics=payload.get("metrics", {}),
		)
