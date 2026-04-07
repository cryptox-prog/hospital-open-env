import asyncio
import json
import os
from typing import List, Optional, Sequence
from openai import OpenAI
from client import HospitalEnv
from models import HospitalAction, Patient, ResourceAssignment, Severity

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-8B-Instruct")

LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "hospital-open-env:local")
API_URL = os.getenv("HOSPITAL_API_URL", "")
BENCHMARK = os.getenv("HOSPITAL_BENCHMARK", "hospital-open-env")
TASK_NAME = os.getenv("HOSPITAL_TASK")

MAX_STEPS = 96
TEMPERATURE = 0.0
MAX_TOKENS = 48

TASK_ORDER: Sequence[str] = (
    "very_easy",
    "easy",
    "easy_medium",
    "medium",
    "medium_hard",
    "hard",
    "difficult",
)

TASK_SUCCESS_THRESHOLDS = {
    "very_easy": 0.62,
    "easy": 0.58,
    "easy_medium": 0.54,
    "medium": 0.50,
    "medium_hard": 0.46,
    "hard": 0.42,
    "difficult": 0.38,
}

BASE_RESOURCE_CONFIG = {
    "doctors": {
        "general": 4,
        "er": 3,
        "radiologist": 2,
        "general_surgeon": 2,
        "cardiothoracic_surgeon": 1,
        "obstetric_surgeon": 1,
    },

    "nurses": {
        "general": 8,
        "er": 6,
        "or": 3
    },

    "scanners": {
        "xray": 2,
        "ct": 1,
        "mri": 1
    },

    "beds": {
        "general": 16,
        "er": 6
    },

    "operating-rooms": 3
}
TASK_CONFIGS = {

    "very_easy": {
        "patients": {
            "count": 18,
            "arrival_spread": "front_loaded",
            "severity_weights": {"low": 65, "medium": 25, "high": 8, "critical": 2}
        }
    },

    "easy": {
        "patients": {
            "count": 26,
            "arrival_spread": "front_loaded",
            "severity_weights": {"low": 50, "medium": 30, "high": 15, "critical": 5}
        }
    },

    "easy_medium": {
        "patients": {
            "count": 34,
            "arrival_spread": "uniform",
            "severity_weights": {"low": 40, "medium": 35, "high": 18, "critical": 7}
        }
    },

    "medium": {
        "patients": {
            "count": 42,
            "arrival_spread": "uniform",
            "severity_weights": {"low": 30, "medium": 35, "high": 23, "critical": 12}
        }
    },

    "medium_hard": {
        "patients": {
            "count": 50,
            "arrival_spread": "peak_hours",
            "severity_weights": {"low": 22, "medium": 33, "high": 27, "critical": 18}
        }
    },

    "hard": {
        "patients": {
            "count": 58,
            "arrival_spread": "peak_hours",
            "severity_weights": {"low": 15, "medium": 30, "high": 30, "critical": 25}
        }
    },

    "difficult": {
        "patients": {
            "count": 66,
            "arrival_spread": "back_loaded",
            "severity_weights": {"low": 10, "medium": 25, "high": 35, "critical": 30}
        }
    },
}

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}

SYSTEM_PROMPT = (
    "You are planning hospital resource allocation. "
    "Return only a JSON array of patient ids in priority order. "
    "Prioritize: CRITICAL > HIGH > MEDIUM > LOW, "
    "then higher condition score, then longest waiting time."
)


# --------------------------------------------------------------------------------
# Log Functions
# --------------------------------------------------------------------------------
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    """print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )"""

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)



# --------------------------------------------------------------------------------
# Tasks Helprer Functions
# --------------------------------------------------------------------------------
def get_task_config(task_name: str) -> dict:
    task = TASK_CONFIGS.get(task_name, TASK_CONFIGS["easy"])
    return {**BASE_RESOURCE_CONFIG, "patients": task["patients"]}

def is_task_enabled(task_name: str) -> bool:
    return TASK_NAME is None or TASK_NAME == task_name or TASK_NAME == "all"


# --------------------------------------------------------------------------------
# Get currently free resources
# --------------------------------------------------------------------------------
def free_resources_by_time(resources, current_quantum: int):
    free_resources = []
    for resource in resources:
        if resource.busy_until_quantum <= current_quantum:
            free_resources.append(resource)
    return free_resources

def free_beds_by_occupancy(beds, current_quantum: int):
    free_beds = []
    for bed in beds:
        if bed.busy_until_quantum <= current_quantum:
            free_beds.append(bed)
    return free_beds


def format_assignment(assignment: ResourceAssignment) -> str:
    # Conver resource assignement struct to string for step logging
    nurse_part = "+".join(assignment.nurse_ids) if assignment.nurse_ids else "none"
    scanner_part = assignment.scanner_id or "none"
    room_part = assignment.operating_room_id or "none"
    doctor_part = ",".join(assignment.doctor_ids) if assignment.doctor_ids else "none"
    return (
        f"{assignment.patient_id}|doc={doctor_part}|nurses={nurse_part}|bed={assignment.bed_id}"
        f"|scan={scanner_part}|or={room_part}"
    )

def summarize_patient(patient: Patient) -> str:
    # Convert patient struct to string for prompt formatting
    scanner = patient.required_scanner.value if patient.required_scanner else "none"
    operation = patient.operation_type.value if patient.operation_type else "none"
    return (
        f"{patient.patient_id}:{patient.severity.value}:cond={patient.condition_score:.1f}:"
        f"wait={patient.waited_quanta}:doc={patient.required_doctor.value}:"
        f"nurse={patient.required_nurse_type.value}x{patient.required_nurses}:"
        f"bed={patient.required_bed_type.value}:scan={scanner}:op={operation}"
    )


def choose_priority_order(client: Optional[OpenAI], state) -> List[str]:
    # a prelinimary order of patients based on severity, condition score, and wait time
    heuristic_order = [
        patient.patient_id
        for patient in sorted(
            state.waiting_patients,
            key=lambda p: (SEVERITY_ORDER[p.severity], -p.condition_score, -p.waited_quanta, p.arrival_quantum),
        )
    ]

    # if no client or not enough patients, return the heuristic order without calling the model
    if client is None or len(heuristic_order) < 2:
        return heuristic_order

    # dont take too many patients for 1 prompt current limit 10
    # TODO: should this be limited ???
    candidates = heuristic_order[: min(10, len(heuristic_order))]
    if not candidates:
        return heuristic_order

    user_prompt = (
        f"Task: Allocate hospital patients at quantum {state.current_quantum}.\n"
        f"Waiting patients: {', '.join(summarize_patient(p) for p in candidates)}\n"
        "Return a JSON array of patient ids in priority order only."
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        raw = (completion.choices[0].message.content or "").strip()

        # extract list from llm response
        start = raw.find("[")
        end = raw.rfind("]")

        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, list):
                # keep the order from the model but filter out any ids that are not in the heuristic order
                parsed = [str(item) for item in data if str(item) in heuristic_order]
                if parsed:
                    remaining = [pid for pid in heuristic_order if pid not in parsed]
                    return parsed + remaining
    except Exception as exc:
        _ = exc
    return heuristic_order


# --------------------------------------------------------------------------------
# Acquire 1 or n resources from res pool, decide if they are the correct using lambda fucntion (predicate)
# --------------------------------------------------------------------------------
def take_first(pool, predicate):
    for index, resource in enumerate(pool):
        if predicate(resource):
            return pool.pop(index)
    return None

def take_n(pool, predicate, count: int):
    taken = []
    for _ in range(count):
        resource = take_first(pool, predicate)
        if resource is None:
            return []
        taken.append(resource)
    return taken


def build_action(state, client: Optional[OpenAI]) -> tuple[HospitalAction, str]:
    priority_ids = choose_priority_order(client, state)
    waiting_by_id = {patient.patient_id: patient for patient in state.waiting_patients}

    available_doctors = free_resources_by_time(state.doctors, state.current_quantum)
    available_nurses = free_resources_by_time(state.nurses, state.current_quantum)
    available_scanners = free_resources_by_time(state.scanners, state.current_quantum)
    available_beds = free_beds_by_occupancy(state.beds, state.current_quantum)
    available_rooms = free_resources_by_time(state.operating_rooms, state.current_quantum)

    assignments: List[ResourceAssignment] = []
    action_parts: List[str] = []

    for patient_id in priority_ids:
        patient = waiting_by_id.get(patient_id)
        if patient is None:
            continue

        doctor = take_first(available_doctors, lambda r, required=patient.required_doctor: r.resource_type == required)
        nurses = take_n(available_nurses, lambda r, required=patient.required_nurse_type: r.resource_type == required, patient.required_nurses)
        bed = take_first(available_beds, lambda r, required=patient.required_bed_type: r.resource_type == required)
        scanner = None
        if patient.required_scanner is not None:
            scanner = take_first(
                available_scanners,
                lambda r, required=patient.required_scanner: r.resource_type == required,
            )
        operating_room = None
        if patient.operation_duration_quanta > 0:
            operating_room = take_first(available_rooms, lambda _: True)

        if doctor is None or len(nurses) < patient.required_nurses or bed is None:
            continue
        if patient.required_scanner is not None and scanner is None:
            continue
        if patient.operation_duration_quanta > 0 and operating_room is None:
            continue

        assignment = ResourceAssignment(
            patient_id=patient.patient_id,
            doctor_ids=[doctor.resource_id],
            nurse_ids=[nurse.resource_id for nurse in nurses],
            scanner_id=scanner.resource_id if scanner is not None else None,
            bed_id=bed.resource_id,
            operating_room_id=operating_room.room_id if operating_room is not None else None,
        )
        assignments.append(assignment)
        action_parts.append(format_assignment(assignment))

    if not assignments:
        return HospitalAction(assignments=[]), "nope"

    return HospitalAction(assignments=assignments), "||".join(action_parts)


async def run_task(task_name: str, client: Optional[OpenAI], env: HospitalEnv) -> None:
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_name, env=BENCHMARK, model=MODEL_NAME)

    try:
        result = await env.reset(config=get_task_config(task_name), seed=42, episode_id=f"{task_name}-episode")

        if client is not None:
            try:
                state = await env.state()
                _ = choose_priority_order(client, state)
            except Exception:
                pass

        for step in range(1, MAX_STEPS + 1):
            if bool(result.done):
                break

            state = await env.state()
            action, action_label = build_action(state, client)

            try:
                result = await env.step(action)
                reward = float(result.reward or 0.0)
                done = bool(result.done)
                rewards.append(reward)
                steps_taken = step
                log_step(step=step, action=action_label, reward=reward, done=done, error=None)
            except Exception as exc:
                log_step(step=step, action=action_label, reward=0.0, done=True, error=str(exc))
                success = False
                break

            if done:
                break

        score = sum(rewards)/1000
        # TODO: Uncomment clamping
        # score = min(max(score, 0.0), 1.0)
        success_threshold = TASK_SUCCESS_THRESHOLDS.get(task_name, 1.0)
        success = score >= success_threshold
    except Exception as exc:
        log_step(step=0, action="", reward=0.0, done=True, error=str(exc))
        success = False
    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


async def main() -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY) if API_KEY else None
    
    if API_URL:
        env = HospitalEnv(API_URL)
        await env.connect()
    else:
        env = await HospitalEnv.from_docker_image(LOCAL_IMAGE_NAME, timeout_s=120)
    
    try:
        tasks = [TASK_NAME] if TASK_NAME and TASK_NAME in TASK_CONFIGS else list(TASK_ORDER)
        for task_name in tasks:
            await run_task(task_name, client, env)
    finally:
        try:
            await env.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())