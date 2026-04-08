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

`hospital-open-env` is an OpenEnv-compatible hospital triage and resource-allocation simulation.
The agent allocates limited medical resources to incoming patients over a 24-hour shift.

## Motivation

During surges (disasters, outbreaks, mass-casualty events), hospitals face two competing goals:

- Treat the most severe patients quickly.
- Maintain throughput so lower-severity queues do not collapse the system.

This environment models that trade-off with realistic constraints (specialists, scanners, ER beds, OR access, wait-driven deterioration), making it a compact benchmark for sequential decision-making under pressure.

## Environment Summary

- **Episode horizon:** 24 hours
- **Time step:** 15 minutes (`96` quanta per episode)
- **Core objective:** maximize weighted discharges while minimizing deaths, excessive waiting, walkouts, and denied admissions
- **Patient flow:** stochastic arrivals with configurable distributions (`uniform`, `front_loaded`, `peak_hours`, etc.)

## Table of Contents

- [Hospital Emergency Environment](#hospital-emergency-environment)
  - [Motivation](#motivation)
  - [Environment Summary](#environment-summary)
  - [Action Space](#action-space)
  - [Observation Space](#observation-space)
  - [Tasks and Expected Difficulty](#tasks-and-expected-difficulty)
  - [Reward Signal](#reward-signal)
  - [Setup](#setup)
  - [Usage](#usage)
  - [Baseline Scores](#baseline-scores)
  - [Table of Contents](#table-of-contents)

## Action Space

At each step, the agent submits a `HospitalAction`:

- `assignments: List[ResourceAssignment]`

Each `ResourceAssignment` contains:

- `patient_id: str`
- `doctor_ids: List[str]`
- `nurse_ids: List[str]`
- `scanner_id: Optional[str]`
- `bed_id: Optional[str]`
- `operating_room_id: Optional[str]`

Assignments are only applied if **all required resources are valid and currently available** for that patient’s clinical needs.

## Observation Space

Each step returns `HospitalObservation` with:

- `done: bool`
- `reward: Optional[float]`
- `current_quantum: int`
- `waiting_patients: int`
- `critical_waiting_patients: int`
- `resources_free: Dict[str, Dict[str, int] | int]`
- `queue_by_severity: Dict[str, int]`
- `message: str`

This gives a compact operational dashboard: time, queue pressure, and free capacity per resource type.

## Tasks and Expected Difficulty

Benchmarks are configured in `inference.py` with fixed seed (`42`) and increasing load/severity.

- **Easy**
  - Patients: `312`
  - Arrivals: `uniform`
  - Severity mix: `low 65%, medium 25%, high 8%, critical 2%`
  - **Expected difficulty:** low (mostly throughput management)

- **Medium**
  - Patients: `312`
  - Arrivals: `front_loaded`
  - Severity mix: `low 35%, medium 35%, high 20%, critical 10%`
  - **Expected difficulty:** moderate (early surge + more high acuity)

- **Hard**
  - Patients: `400`
  - Arrivals: `peak_hours`
  - Severity mix: `low 20%, medium 35%, high 25%, critical 20%`
  - **Expected difficulty:** high (sustained critical load and resource contention)

Success thresholds used by the runner:

- `easy >= 0.25`
- `medium >= 0.10`
- `hard >= 0.05`

## Reward Signal

Per step reward increases with discharges (higher weight for higher severity) and decreases with deaths, waiting burden, denied admissions, and patients leaving. It is then normalized by total patient count for the episode.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Build the environment image:

```bash
docker build -t hospital-open-env:local .
```

3. (Optional) Configure `.env` values:

```conf
HF_TOKEN=hf_***
API_KEY=hf_***
API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=Qwen/Qwen2.5-7B-Instruct
IMAGE_NAME=hospital-open-env:local
HOSPITAL_TASK=all
```

If no API key is provided, the runner uses deterministic heuristic prioritization.

## Usage

- Run all tasks:

```bash
python inference.py
```

- Run one task:

```bash
HOSPITAL_TASK=easy python inference.py
```

- Validate OpenEnv submission flow:

```bash
./validate-submission.sh <your-space-url>
```

