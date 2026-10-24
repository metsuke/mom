#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from ingest_agent import MOMMultilingualIngestionAgent
from ai_cluster_manager import load_ai_config, check_colibri_status

class MOMAIClient:
    """Cliente HTTP ligero sin dependencias externas para interactuar con la API OpenAI de Colibrì."""

    def __init__(self, api_base: str = "http://127.0.0.1:8000/v1", model: str = "Qwen3.6-35B-A3B", timeout: int = 30):
        self.api_base = api_base.rstrip('/')
        self.model = model
        self.timeout = timeout

    def completion(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        url = f"{self.api_base}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MOM-AIIngestAgent/0.8.1"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status == 200:
                    res_data = json.loads(response.read().decode("utf-8"))
                    choices = res_data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"⚠️ Error consultando API local de IA ({url}): {e}")
        return None

class MOMAIIngestionAgent(MOMMultilingualIngestionAgent):
    """Agente de ingesta extendido asistido por IA local/remota (Colibrì)."""

    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        cfg = load_ai_config()
        
        # Selecciona el primer endpoint disponible de la lista de nodos
        nodes = cfg.get("nodes", [])
        if nodes:
            self.api_base = nodes[0].get("api_base", "http://127.0.0.1:8000/v1")
        else:
            self.api_base = cfg.get("api_base", "http://127.0.0.1:8000/v1")
            
        self.model = cfg.get("active_model", "Qwen3.6-35B-A3B")
        self.ai_client = MOMAIClient(api_base=self.api_base, model=self.model)

    def is_ai_available(self) -> bool:
        status = check_colibri_status(self.api_base, timeout=2)
        return status.get("online", False)

    def translate_paragraph_es(self, text_en: str) -> Optional[str]:
        """Solicita a Colibrì una traducción técnica limpia de EN a ES."""
        system_prompt = (
            "Eres un traductor técnico experto especializado en documentación de ingeniería y estándares ESA/MOM. "
            "Traduce el siguiente texto del inglés al español de forma fiel, precisa y concisa. "
            "Devuelve ÚNICAMENTE el texto traducido sin introducciones ni comentarios adicionales."
        )
        return self.ai_client.completion(prompt=text_en, system_prompt=system_prompt)

if __name__ == "__main__":
    data_directory = current_dir.parent / "data"
    agent = MOMAIIngestionAgent(data_dir=data_directory)
    print(f"🤖 Agente Ingestor IA inicializado.")
    print(f"  • Endpoint Colibrì: {agent.api_base}")
    print(f"  • Modelo activo: {agent.model}")
    print(f"  • Estado API local: {'✅ ONLINE' if agent.is_ai_available() else '❌ OFFLINE'}")

# App Version: 0.8.1
# Script Version: 0.8.1.4
# Compatible Schema: 0.5.3