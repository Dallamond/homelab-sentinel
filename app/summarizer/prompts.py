"""
Construcción de prompts para los resúmenes periódicos y para la
explicación bajo demanda de un evento/alerta concreto.
"""
from __future__ import annotations

import json

SYSTEM_CONTEXT = (
    "Eres un asistente de un sysadmin que gestiona un homelab personal "
    "(Proxmox, NAS, varios contenedores Docker). Analiza los datos agregados "
    "de logs y alertas que te paso y escribe un resumen claro en español, en "
    "formato markdown, pensado para leerse en 1-2 minutos."
)


def build_period_summary_prompt(period: str, stats: dict) -> str:
    return f"""{SYSTEM_CONTEXT}

Periodo: {period}
Datos agregados (JSON):
{json.dumps(stats, indent=2, ensure_ascii=False, default=str)}

Escribe el resumen con estas secciones markdown:
## Resumen general
Una o dos frases sobre cómo ha ido el periodo en general.

## Puntos destacados
Lista de lo más relevante: picos de errores, servicios problemáticos, tendencias.

## Alertas críticas
Si hubo alertas critical/error, resúmelas. Si no hubo, dilo explícitamente.

## Recomendaciones
2-4 consejos concretos y accionables basados en los datos (por ejemplo: revisar
un servicio que falla repetidamente, vigilar espacio en disco, rotar logs, etc.).
No inventes datos que no estén en el JSON.
"""


def build_explain_prompt(source_name: str, severity: str, message: str, raw: str) -> str:
    return f"""{SYSTEM_CONTEXT}

Un usuario no técnico-experto te pide que le expliques esta línea de log
porque le resulta rara o no la entiende bien:

Origen: {source_name}
Severidad: {severity}
Mensaje: {message}
Línea original: {raw}

Explica en 3-6 frases, en español y sin tecnicismos innecesarios:
1) qué significa este mensaje,
2) si es motivo de preocupación real o es normal/benigno,
3) qué acción (si alguna) debería tomar.
Si no tienes contexto suficiente para estar seguro, dilo honestamente en vez
de inventar una causa.
"""
