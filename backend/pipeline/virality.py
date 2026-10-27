"""
Virality filter — separate pass to maximize viewer retention.

Inspired by proven YouTube strategy:
1. Rate hook (1-10), rewrite if below 8
2. Find 3 weakest click-away moments, add curiosity loops
3. Add pattern interrupts every 90 seconds
"""

import logging
from backend.config import get_model_config
from backend.utils.llm import call_llm

logger = logging.getLogger(__name__)


async def apply_virality_filter(
    script: str,
    lang: str,
    niche: str = "finance",
) -> str:
    """
    Run script through virality filter to maximize retention.
    
    This is a SEPARATE pass after script improvement.
    Focuses on: hooks, click-away prevention, pattern interrupts.
    
    Args:
        script: Improved script text
        lang: Language code (de, es)
        niche: Content niche for context
    
    Returns:
        Virality-optimized script
    """
    model_config = get_model_config("virality_filter")
    
    if lang == "de":
        prompt = _build_prompt_de(script, niche)
    elif lang == "es":
        prompt = _build_prompt_es(script, niche)
    else:
        prompt = _build_prompt_en(script, niche)
    
    result = await call_llm(
        prompt=prompt,
        model=model_config["primary"],
        temperature=0.35,
        max_tokens=model_config["max_tokens"],
        fallback_model=model_config.get("fallback"),
    )
    
    # Extract just the script (remove analysis if present)
    script_out = _extract_script(result)
    
    logger.info(f"Virality filter applied: {len(script)} → {len(script_out)} chars")
    return script_out


def _build_prompt_de(script: str, niche: str) -> str:
    return f"""Du bist ein YouTube-Stratege, der über 10.000 virale {niche}-Videos auf Deutsch analysiert hat.

Überprüfe das folgende Skript und mache DREI Dinge:

1. HOOK BEWERTUNG: Bewerte den Hook (erste 30 Sekunden) von 1 bis 10.
   - Unter 8? Schreibe ihn komplett um.
   - Ein guter Hook startet mit einem konkreten, überraschenden Fakt oder einer Situation, die den Zuschauer sofort betrifft.
   - KEIN Gruß, KEINE Vorstellung, KEIN "In diesem Video..."

2. SCHWACHE STELLEN: Finde die 3 schwächsten Momente, wo ein Zuschauer wegklicken würde.
   - Schreibe jeden um mit einer OFFENEN FRAGE oder einem NEUGIERDE-LOOP.
   - "Aber das war noch nicht das Schlimmste..." 
   - "Was dann passierte, hat selbst Experten überrascht..."
   - Jede schwache Stelle muss neue Spannung aufbauen.

3. PATTERN INTERRUPTS: Füge alle 90 Sekunden (ca. alle 750-800 Zeichen) EINEN Unterbrecher ein:
   - Eine schockierende Statistik mit konkreter Quelle
   - Eine kontraintuitive Behauptung ("Die meisten denken X, aber in Wirklichkeit...")
   - Eine direkte Frage an den Zuschauer ("Was würdest du in dieser Situation tun?")
   - Ein rhetorischer Vergleich ("Das ist so, als würdest du...")

REGELN:
- Gib NUR das überarbeitete Skript zurück — KEINEN Kommentar, KEINE Analyse
- Halte die Gesamtlänge bei ±5% des Originals
- Behalte alle Fakten, Quellen und Zahlen bei
- Der Ton muss natürlich und menschlich bleiben — nicht übertrieben dramatisch
- Schreibe auf Deutsch

SKRIPT:
{script}"""


def _build_prompt_es(script: str, niche: str) -> str:
    return f"""Eres un estratega de YouTube que ha analizado más de 10,000 videos virales de {niche} en español.

Revisa el siguiente guión y haz TRES cosas:

1. EVALUACIÓN DEL GANCHO: Califica el gancho (primeros 30 segundos) del 1 al 10.
   - ¿Menos de 8? Reescríbelo completamente.
   - Un buen gancho empieza con un dato concreto y sorprendente o una situación que el espectador siente como propia.
   - SIN saludo, SIN presentación, SIN "En este video..."

2. PUNTOS DÉBILES: Encuentra los 3 momentos más débiles donde un espectador haría clic en otro video.
   - Reescribe cada uno con una PREGUNTA ABIERTA o un BUCLE DE CURIOSIDAD.
   - "Pero eso no fue lo peor..."
   - "Lo que pasó después sorprendió hasta a los expertos..."
   - Cada punto débil debe generar nueva tensión.

3. INTERRUPCIONES DE PATRÓN: Añade cada 90 segundos (~750-800 caracteres) UNA interrupción:
   - Una estadística impactante con fuente concreta
   - Una afirmación contraintuitiva ("La mayoría piensa X, pero en realidad...")
   - Una pregunta directa al espectador ("¿Qué harías tú en esta situación?")
   - Una comparación retórica ("Es como si tú...")

REGLAS:
- Devuelve SOLO el guión revisado — SIN comentarios, SIN análisis
- Mantén la longitud total en ±5% del original
- Conserva todos los datos, fuentes y cifras
- El tono debe ser natural y humano — no exageradamente dramático
- Escribe en español neutro (comprensible para España y Latinoamérica)

GUIÓN:
{script}"""


def _build_prompt_en(script: str, niche: str) -> str:
    return f"""You are a YouTube strategist who has analyzed 10,000+ viral {niche} videos.

Review the following script and do THREE things:

1. HOOK RATING: Rate the hook (first 30 seconds) from 1 to 10.
   - Below 8? Rewrite it completely.
   - A great hook opens with a concrete, surprising fact or a relatable scenario that makes viewers think "that's exactly me."
   - NO greeting, NO intro, NO "In this video..."

2. WEAK SPOTS: Find the 3 weakest moments where a viewer would click away.
   - Rewrite each to add a CURIOSITY LOOP or OPEN TENSION.
   - "But that wasn't even the worst part..."
   - "What happened next shocked even the experts..."
   - Each weak spot must build new tension.

3. PATTERN INTERRUPTS: Add one interrupt every 90 seconds (~750-800 characters):
   - A shocking statistic with concrete source
   - A counterintuitive claim ("Most people think X, but actually...")
   - A direct question to the viewer ("What would you do?")
   - A rhetorical comparison ("That's like...")

RULES:
- Return ONLY the revised script — NO commentary, NO analysis
- Keep total length within ±5% of original
- Preserve all facts, sources, and numbers
- Tone must stay natural and human — not overdramatic
- Write in English

SCRIPT:
{script}"""


def _extract_script(response: str) -> str:
    """Remove any analysis/commentary, keep just the script."""
    # If response contains markdown headers for analysis, strip them
    lines = response.strip().split("\n")
    
    # Check if there's a clear script section
    script_start = 0
    for i, line in enumerate(lines):
        lower = line.lower().strip()
        if any(marker in lower for marker in [
            "revised script", "überarbeitetes skript", "guión revisado",
            "---", "===",
        ]):
            script_start = i + 1
            break
    
    result = "\n".join(lines[script_start:]).strip()
    
    # Remove trailing analysis if present
    end_markers = ["## analysis", "## analyse", "## análisis", "---", "note:"]
    for marker in end_markers:
        idx = result.lower().rfind(marker)
        if idx > len(result) * 0.8:  # Only if near the end
            result = result[:idx].strip()
    
    return result if result else response.strip()
