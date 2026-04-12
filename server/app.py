import html
import json
import os
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import urlopen

from openenv.core.env_server import create_fastapi_app
from fastapi.responses import HTMLResponse
from models import HospitalAction, HospitalObservation
from server.environment import HospitalEnvironment

app = create_fastapi_app(HospitalEnvironment, HospitalAction, HospitalObservation)
APP_STARTED_AT_UTC = datetime.now(timezone.utc)


def _space_id() -> str | None:
	space_id = os.getenv("SPACE_ID")
	if space_id:
		return space_id

	author = os.getenv("SPACE_AUTHOR_NAME")
	repo = os.getenv("SPACE_REPO_NAME")
	if author and repo:
		return f"{author}/{repo}"

	return None


def _fmt_iso_utc(value: str) -> str | None:
	try:
		parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
		return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
	except ValueError:
		return None


def _get_last_space_update_label() -> str:
	space_id = _space_id()
	if space_id:
		url = f"https://huggingface.co/api/spaces/{space_id}"
		try:
			with urlopen(url, timeout=3) as response:
				payload = json.loads(response.read().decode("utf-8"))
			for key in ("lastModified", "updatedAt", "lastCommit"):
				value = payload.get(key)
				if isinstance(value, str):
					formatted = _fmt_iso_utc(value)
					if formatted:
						return f"Last Space update: {formatted}"
		except (URLError, TimeoutError, json.JSONDecodeError, OSError):
			pass

	return "Server started: " + APP_STARTED_AT_UTC.strftime("%Y-%m-%d %H:%M UTC")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
	last_space_update = html.escape(_get_last_space_update_label())
	return """
	<!doctype html>
	<html>
	  <head>
		<meta charset='utf-8' />
		<meta name='viewport' content='width=device-width, initial-scale=1' />
		<title>Hospital OpenEnv</title>
		<style>
		  :root {
			--bg-main: #f9f5d7;
			--bg-dull: #f9f5d7;
			--bg-surface: #f2e5bc;
			--text-primary: #3c3836;
			--text-secondary: #504945;
			--text-muted: #665c54;
			--accent-green: #98971a;
			--accent-blue: #458588;
			--border-strong: #bdae93;
		  }

		  html, body {
			height: 100dvh;
			margin: 0;
			padding: 0;
		  }

		  body {
			display: grid;
			place-items: center;
			background: var(--bg-main);
			font-family: 'Josefin Sans', system-ui, sans-serif;
			color: var(--text-primary);
			padding: 1rem;
			box-sizing: border-box;
		  }

		  .card {
			width: min(760px, 100%);
			border: 4px dashed var(--border-strong);
			background: var(--bg-dull);
			padding: 1.2rem 1.4rem;
			box-sizing: border-box;
		  }

		  .card:hover {
			background: var(--bg-surface);
		  }

		  h1 {
			margin: 0 0 0.35rem 0;
			font-size: 1.35rem;
			color: var(--text-primary);
			text-align: center;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 0.55rem;
		  }

		  .status-dot {
			width: 0.72rem;
			height: 0.72rem;
			border-radius: 999px;
			background: var(--accent-green);
			display: inline-block;
		  }

		  p {
			margin: 0 0 0.75rem 0;
			color: var(--text-secondary);
		  }

		  .details {
			margin: 0.5rem 0 0 0;
			padding: 0;
			list-style: none;
			display: grid;
			gap: 0.35rem;
			font-size: 0.95rem;
			color: var(--text-muted);
		  }

		  code {
			background: var(--bg-surface);
			padding: 2px 6px;
			border: 1px solid var(--border-strong);
			color: var(--text-primary);
		  }

		  a {
			color: var(--accent-blue);
			font-weight: 700;
			text-decoration: none;
		  }
		</style>
	  </head>
	  <body>
		<section class='card'>
		  <h1><span class='status-dot' aria-hidden='true'></span>Hospital OpenEnv is running<span class='status-dot' aria-hidden='true'></span></h1>
		  <p>OpenEnv hospital resource allocation simulation server.</p>
		  <ul class='details'>
			<li>API docs: <a href='/docs'><code>/docs</code></a></li>
			<li>OpenAPI spec: <a href='/openapi.json'><code>/openapi.json</code></a></li>
			<li>__LAST_SPACE_UPDATE__</li>
			<li>Status: Ready to accept environment requests</li>
		  </ul>
		</section>
	  </body>
	</html>
	""".replace("__LAST_SPACE_UPDATE__", last_space_update)


def main(host: str = "0.0.0.0", port: int = 7860):
	import uvicorn

	uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
	main()