from openenv.core.env_server import create_fastapi_app
from models import HospitalAction, HospitalObservation
from server.environment import HospitalEnvironment

app = create_fastapi_app(HospitalEnvironment, HospitalAction, HospitalObservation)