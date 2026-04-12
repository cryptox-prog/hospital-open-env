---
title: hospital-open-env
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
tags:
  - openenv
---

# Hospital Emergency Environment

## Motivation

In situations like natural disasters or pandemics, the resources of a hospital are often stretched thin. The allocation of resources becomes a important task, one which humans are ill suited for. This environment aims to provide a environment to simulate such conditions.

## Environment Description

- The environment simulates a 24 hour workday
    - The minimum time quantum is of 15 minutes, i.e., 96 steps in every single episode
    - The arrivals stop after hour 20
- There are different types of patient flows made available:
    - `front-loaded` - Most of the patients arrive initially
    - `back-loaded` - Most of the patients arrive at the end
    - `uniform` - The patients arrive in a uniform manner
    - `peak hours` - The patients are 3 times more likely to arrive at certain peak hours
- There are different severities of patients they which are assigned at runtime:
    - `critical`
    - `high`
    - `medium`
    - `low`
- Once the treatment of a patient starts they will not die
- The `low` and `medium` patients leave once they wait too long
- The `high` patient becomes critical once they wait too long
- The `critical` patient dies once it waits for too long
- The hospital has max capacity beyond which no patient will be allowed inside until the patients either die, leave or get discharged
- The agent will be rewarded for starting the treatments of patients. The rewards are different for different severity
    - Only the advancement from waiting to active is rewarded because that is the only thing in the agents control
    - This is also the reason the patients are not dying after being assigned treatment as the patient had little to do with patients dying after they were alloted necessary resources in current environment setup
- The agent will be penalized for:
    - The deaths occurring in a step
    - The `high` severity patients advancing to `critical` severity
    - The total amount of waiting the current patients have done
    - The patients which leave this step due to long wait
    - The patients which get denied admission because the hospital has reached its capacity
    - The reward function utilized the tanh function to squish the scores between 0 and 1

## Action Space

At each step, the agent submits a HospitalAction: `assignments: List[ResourceAssignment]`

Each ResourceAssignment contains:
```python
patient_id: str
doctor_ids: List[str]
nurse_ids: List[str]
scanner_id: Optional[str]
bed_id: Optional[str]
operating_room_id: Optional[str]
```

Assignments are only applied if all required resources are valid and currently available for that patient needs.

## Observation Space

Each step returns HospitalObservation with:

```python
done: bool
reward: Optional[float]
current_quantum: int
waiting_patients: int
critical_waiting_patients: int
resources_free: Dict[str, Dict[str, int] | int]
queue_by_severity: Dict[str, int]
message: str
```

## Running The Environment

- It can be accessed at: `https://pranamud123-hospital-open-env.hf.space`
- It can be locally run using `docker` (hosted at localhost 7860):

```shell
docker build -t hospital-open-env:local -f Dockerfile .
docker run hospital-open-env:local
```

- It can also be run locally with: 
```shell
uvicorn server.app:app  --host 0.0.0.0 --port 7860
```

## Testing

For `inference.py` run have the following environment variables set:
- `API_KEY` - The key of the llm api to call
- `API_BASE_URL` - The base url where the llm is hosted
- `MODEL_NAME` - The name of the model to test with
- `LOCAL_IMAGE_NAME` - The name of the local docker image (to run locally)
- `API_URL` - The url to the environment host
- `TASK_NAME` - One of: easy, medium, hard, all

