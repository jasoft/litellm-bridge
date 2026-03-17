import os

CONFIG_PATH = os.environ.get("LITELLM_CONFIG_PATH", "/app/config.yaml")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = os.environ.get("PORT", "8046")


def main() -> None:
    if not os.environ.get("ELEVENLABS_API_KEY"):
        raise ValueError("ELEVENLABS_API_KEY is required")

    os.execvp(
        "litellm",
        [
            "litellm",
            "--host",
            HOST,
            "--port",
            PORT,
            "--config",
            CONFIG_PATH,
        ],
    )

if __name__ == "__main__":
    main()
