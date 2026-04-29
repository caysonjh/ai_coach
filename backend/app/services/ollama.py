import platform
import shutil
import subprocess
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import get_settings


class OllamaStatus(BaseModel):
    running: bool
    base_url: str
    configured_model: str
    embedding_model: str
    installed_models: list[str] = []
    configured_model_installed: bool = False
    embedding_model_installed: bool = False
    can_start: bool = False
    message: str = ""


class OllamaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def status(self) -> OllamaStatus:
        installed = await self.installed_models()
        running = installed is not None
        installed_models = installed or []
        return OllamaStatus(
            running=running,
            base_url=self.settings.ollama_base_url,
            configured_model=self.settings.ollama_model,
            embedding_model=self.settings.ollama_embed_model,
            installed_models=installed_models,
            configured_model_installed=self._model_present(self.settings.ollama_model, installed_models),
            embedding_model_installed=self._model_present(self.settings.ollama_embed_model, installed_models),
            can_start=self._can_start_ollama(),
            message=self._status_message(running, installed_models),
        )

    async def ensure_running(self) -> OllamaStatus:
        status = await self.status()
        if status.running:
            return status

        started = self._start_ollama()
        if not started:
            status.message = (
                "Ollama is not running and the backend could not find a way to start it. "
                "Install Ollama or run `ollama serve` manually."
            )
            return status

        for _ in range(20):
            time.sleep(0.5)
            status = await self.status()
            if status.running:
                return status

        status.message = "Ollama start was attempted, but the API did not become reachable."
        return status

    async def installed_models(self) -> list[str] | None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                response.raise_for_status()
                return [item["name"] for item in response.json().get("models", [])]
        except Exception:
            return None

    async def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any] | None:
        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0.2},
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(f"{self.settings.ollama_base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content")
                if not content:
                    return None
                return httpx.Response(200, content=content).json()
        except Exception:
            return None

    def _status_message(self, running: bool, installed_models: list[str]) -> str:
        if not running:
            return "Ollama is not reachable. Use the start button or run `ollama serve`."
        missing = []
        if not self._model_present(self.settings.ollama_model, installed_models):
            missing.append(self.settings.ollama_model)
        if not self._model_present(self.settings.ollama_embed_model, installed_models):
            missing.append(self.settings.ollama_embed_model)
        if missing:
            pulls = ", ".join(f"`ollama pull {model}`" for model in missing)
            return f"Ollama is running, but missing model(s): {pulls}."
        return "Ollama is running and the configured models are installed."

    def _model_present(self, desired: str, installed_models: list[str]) -> bool:
        desired_base = desired.split(":")[0]
        return any(model == desired or model.split(":")[0] == desired_base for model in installed_models)

    def _can_start_ollama(self) -> bool:
        return platform.system() == "Darwin" or shutil.which("ollama") is not None

    def _start_ollama(self) -> bool:
        try:
            if platform.system() == "Darwin":
                subprocess.Popen(
                    ["open", "-a", "Ollama"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            ollama = shutil.which("ollama")
            if ollama:
                subprocess.Popen(
                    [ollama, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
        except Exception:
            return False
        return False

    async def embed(self, text: str) -> list[float] | None:
        payload = {"model": self.settings.ollama_embed_model, "input": text}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{self.settings.ollama_base_url}/api/embed", json=payload)
                response.raise_for_status()
                embeddings = response.json().get("embeddings", [])
                return embeddings[0] if embeddings else None
        except Exception:
            return None
