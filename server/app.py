from openenv.core.env_server import create_fastapi_app
from environment import HospitalEnvironment

app = create_fastapi_app(HospitalEnvironment)