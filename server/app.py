from openenv.core.env_server import create_fastapi_app
from models import HospitalAction, HospitalObservation
from server.environment import HospitalEnvironment

app = create_fastapi_app(HospitalEnvironment, HospitalAction, HospitalObservation)


def main(host: str = "0.0.0.0", port: int = 7860):
	import uvicorn

	uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
	main()