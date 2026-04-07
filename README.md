# Hospital Emergency Environment

A hospital environment overburdened with patients, the agent must allocate the different resources

- Different types of doctors
- Different types of scanners
- Beds
- Operating rooms
- Nurses

To different patients ensuring the optimal condition for most patients during a 24 hour run.

## Table of Contents

- [Hospital Emergency Environment](#hospital-emergency-environment)
  - [Table of Contents](#table-of-contents)
  - [Why Hospital Resources](#why-hospital-resources)
  - [Environment](#environment)
  - [Development](#development)

## Why Hospital Resources

At times of great emergency like natural disasters, stampedes, and pandemics, hospitals often are overcome with patients. At such times, it becomes necessary for them to get the best outcome for the most patients. This will help explore how such a task can be done.

## Environment

smth smth

## Development

Sample Env

```conf
HF_TOKEN=hf_***
API_KEY=hf_***

LOCAL_IMAGE_NAME=hospital-open-env:latest

API_BASE_URL=https://router.huggingface.co/v1
MODEL_NAME=Qwen/Qwen3-8B-Instruct

HOSPITAL_TASK=all
MY_ENV_V4_BENCHMARK=1
```

Docker build

```shell
docker build -t hospital-open-env:local -f server/Dockerfile .
```

Run

```shell
python inference.py
```
