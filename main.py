import litellm
from litellm.proxy.proxy_server import ProxyConfig, initialize
import os
import asyncio

# Set global flags before initialization
litellm.drop_params = True
litellm.set_verbose = True

async def main():
    config_path = "/app/config.yaml"
    # The proxy usually runs as a standalone server, we use the internal initialization logic
    # consistent with what 'litellm --config ...' does
    from litellm.proxy.proxy_server import run_proxy_server
    
    # We pass the same args as the CLI would
    run_proxy_server(
        host="0.0.0.0",
        port=8046,
        config=config_path
    )

if __name__ == "__main__":
    if not os.environ.get("ELEVENLABS_API_KEY"):
        raise ValueError("ELEVENLABS_API_KEY is required")
    
    import uvicorn
    from litellm.proxy.proxy_server import app
    
    # Manually initialize the proxy with our config
    async def startup():
        proxy_config = ProxyConfig()
        await proxy_config.load_config(router=None, config_file_path="/app/config.yaml")
        await initialize(config="/app/config.yaml", proxy_logging_obj=None)

    # Use uvicorn to run the app, but ensure we initialize litellm first
    # LiteLLM proxy is a FastAPI app
    
    # Actually, the simplest way is to use the litellm CLI but inject the flag 
    # via a custom entrypoint script that imports litellm first.
    # But let's try this standard way:
    uvicorn.run("litellm.proxy.proxy_server:app", host="0.0.0.0", port=8046, log_level="info")
