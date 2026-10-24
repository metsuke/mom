#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

# Garantiza la importación limpia de los módulos hermanos de mom-py
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

CONFIG_AI_PATH = current_dir.parent / "data" / "config_ai.json"
CONFIG_AI_TEMPLATE_PATH = current_dir.parent / "data" / "config_ai.json.template"
MIRROR_REPO_URL = "https://github.com/metsuos/colibri-metsuos"

def load_ai_config() -> Dict[str, Any]:
    """
    Carga la configuración del clúster de IA desde data/config_ai.json.
    Si no existe, lee data/config_ai.json.template o genera la estructura multinodo/multimáquina.
    """
    default_config = {
        "active_model": "Qwen3.6-35B-A3B",
        "timeout_seconds": 2,
        "nodes": [
            {
                "name": "Nodo Local Colibrì (iMac 2017)",
                "api_base": "http://127.0.0.1:8000/v1"
            },
            {
                "name": "Nodo Remoto Ryzen 1 (GPU/RAM)",
                "api_base": "http://192.168.1.50:8000/v1"
            },
            {
                "name": "Nodo Remoto Ryzen 2 (Jan/Colibrì)",
                "api_base": "http://192.168.1.51:8000/v1"
            }
        ]
    }

    if CONFIG_AI_PATH.exists():
        try:
            with open(CONFIG_AI_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                default_config.update(user_cfg)
                return default_config
        except Exception as e:
            print(f"⚠️ Advertencia: No se pudo leer {CONFIG_AI_PATH}: {e}")

    if CONFIG_AI_TEMPLATE_PATH.exists():
        try:
            with open(CONFIG_AI_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                tmpl_cfg = json.load(f)
                default_config.update(tmpl_cfg)
                # Si la plantilla leída trae nodos, los respetamos íntegramente
                return default_config
        except Exception as e:
            print(f"⚠️ Advertencia: No se pudo leer {CONFIG_AI_TEMPLATE_PATH}: {e}")

    # Escribe la configuración de IA en disco para persistencia aislada
    try:
        CONFIG_AI_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_AI_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Advertencia: No se pudo crear {CONFIG_AI_PATH}: {e}")

    return default_config

def check_colibri_status(api_base: str, timeout: int = 2) -> Dict[str, Any]:
    """Sondea el endpoint /v1/models de un nodo Colibrì concreto para descubrir sus modelos disponibles."""
    url = f"{api_base.rstrip('/')}/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MOM-AIClusterManager/0.8.1"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models = [m.get("id", "desconocido") for m in data.get("data", [])]
                return {"online": True, "models": models}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        pass
    return {"online": False, "models": []}

def confirm_and_select_profile() -> Dict[str, Any]:
    """
    Escanea e informa del estado de TODAS las máquinas/nodos de IA definidos en la configuración.
    """
    ai_cfg = load_ai_config()
    timeout = ai_cfg.get("timeout_seconds", 2)
    current_model = ai_cfg.get("active_model", "Qwen3.6-35B-A3B")

    # Mapea los nodos; si la configuración es antigua y solo tenía api_base, la convierte a lista
    nodes_def = ai_cfg.get("nodes", [])
    if not nodes_def and "api_base" in ai_cfg:
        nodes_def = [{"name": "Nodo Principal", "api_base": ai_cfg["api_base"]}]

    print("\n--- 🤖 GESTOR DEL CLUSTER DE IA LOCAL Y REMOTO (COLIBRÌ) ---")
    print(f"Modelo activo asignado al pipeline MOM: {current_model}")
    print(f"Sondeando {len(nodes_def)} máquinas/nodos registrados (timeout: {timeout}s)...")
    print("-" * 65)

    cluster_report = []
    any_online = False

    for idx, node in enumerate(nodes_def, 1):
        name = node.get("name", f"Nodo-{idx}")
        api_base = node.get("api_base", "http://127.0.0.1:8000/v1")
        
        status = check_colibri_status(api_base, timeout=timeout)
        node_entry = {
            "name": name,
            "api_base": api_base,
            "status": "ONLINE" if status["online"] else "OFFLINE",
            "detected_models": status["models"]
        }
        cluster_report.append(node_entry)

        if status["online"]:
            any_online = True
            print(f"✅ [{idx}/{len(nodes_def)}] {name} ({api_base}): ONLINE")
            print(f"     • Modelos detectados ({len(status['models'])}): {', '.join(status['models'])}")
        else:
            print(f"❌ [{idx}/{len(nodes_def)}] {name} ({api_base}): OFFLINE / INACCESIBLE")

    print("-" * 65)
    if not any_online:
        print(f"⚠️ No se detectó ninguna máquina activa de Colibrì.")
        print(f"🔗 Consulta el espejo oficial si necesitas configuración local o remota:")
        print(f"   👉 {MIRROR_REPO_URL}\n")

    return {
        "cluster_status": "ONLINE" if any_online else "OFFLINE",
        "active_model": current_model,
        "nodes_scanned": len(nodes_def),
        "nodes": cluster_report
    }

if __name__ == "__main__":
    res = confirm_and_select_profile()
    print("\nResumen detallado de la infraestructura de IA:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

# App Version: 0.8.1
# Script Version: 0.8.1.4
# Compatible Schema: 0.5.3