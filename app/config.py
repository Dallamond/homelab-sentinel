"""
Configuración central de la aplicación.
Todo se lee de variables de entorno (ver .env.example) con valores por defecto
razonables para desarrollo local.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Union

import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Rol de esta instancia ---
    # "standalone": agente + servidor en el mismo proceso (un solo host, lo más simple).
    # "server": solo servidor central (DB, API, dashboard, alertas, resúmenes).
    # "agent": solo agente (descubre y envía logs a un servidor remoto).
    role: Literal["standalone", "server", "agent"] = "standalone"
    host_name: str = Field(default="homelab", description="Nombre identificativo de este host (ej. 'nas', 'minipc').")

    # --- Base de datos (solo aplica a role=server|standalone) ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/sentinel.db",
        description="URL de conexión SQLAlchemy. Usa postgresql+asyncpg://... si quieres escalar.",
    )

    # --- Servidor remoto (solo aplica a role=agent) ---
    server_url: str = Field(default="http://localhost:8088", description="URL del servidor central al que este agente envía eventos.")
    agent_api_key: str = Field(default="change-me", description="Token compartido entre agente y servidor.")
    agent_push_interval_seconds: int = 5
    agent_discovery_interval_seconds: int = 60
    agent_push_max_buffer: int = Field(default=5000, description="Tope de eventos en memoria si el servidor central está caído.")

    # --- Collectors ---
    # Listas de filtro opcionales: si están vacías se vigila TODO lo descubierto.
    # - journald_units: lista de unidades systemd a seguir (ej. ["immich.service"]).
    # - docker_containers: lista de prefijos/uñames de contenedores a seguir.
    collect_journald: bool = Field(default=True)
    collect_docker: bool = Field(default=True)
    docker_socket: str = Field(default="unix:///var/run/docker.sock")
    # Fuentes que se excluyen del feed por defecto. Suele usarse para no
    # monitorizar el propio Sentinel: el dashboard hace polling a /api/* cada
    # pocos segundos y eso genera cientos de "200 OK" inútiles.
    excluded_sources: Union[list[str], str] = Field(default_factory=lambda: ["homelab-sentinel"])
    # Normalizamos los campos de lista vía field_validator: pydantic-settings
    # intenta json.loads() sobre los valores complejos y, si no parsean, lanza
    # SettingsError. El tipo Union hace que los fallos de parseo NO sean
    # fatales y deja pasar el string crudo a nuestro validador.
    journald_units: Union[list[str], str] = Field(default_factory=list)
    docker_containers: Union[list[str], str] = Field(default_factory=list)

    # --- Reglas de alertas (solo role=server|standalone) ---
    rules_path: Path = Field(default=BASE_DIR / "rules.yaml")

    # --- Notificadores ---
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    # --- Summarizer (resúmenes semanales/mensuales + explicación bajo demanda) ---
    summarizer_backend: Literal["gemini", "ollama", "openai_compat", "none"] = "gemini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    openai_compat_base_url: str = ""
    openai_compat_api_key: str = ""
    openai_compat_model: str = ""

    weekly_summary_cron: str = "0 8 * * MON"
    monthly_summary_cron: str = "0 8 1 * *"

    # --- API / Dashboard ---
    api_host: str = "0.0.0.0"
    api_port: int = 8088
    cors_origins: Union[list[str], str] = Field(default_factory=lambda: ["*"])
    # Si está vacío, el dashboard queda abierto (modo LAN). Si se rellena, el
    # frontend pide la clave y la manda como X-Dashboard-Key.
    dashboard_api_key: str = Field(default="", description="Clave opcional para proteger el dashboard y los endpoints de lectura.")
    llm_rate_limit_explain: int = Field(default=20, description="Máx. llamadas a /api/explain por IP y ventana.")
    llm_rate_limit_summary: int = Field(default=6, description="Máx. llamadas a /api/summaries/generate por IP y ventana.")
    llm_rate_limit_window_seconds: int = Field(default=3600)

    @field_validator("journald_units", "docker_containers", "cors_origins", "excluded_sources", mode="before")
    @classmethod
    def _split_space_or_csv(cls, value):
        """Acepta JSON, lista, o string separado por espacios/comas."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):  # JSON: '["a", "b"]'
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in stripped.replace(",", " ").split() if item.strip()]
        return value


settings = Settings()
