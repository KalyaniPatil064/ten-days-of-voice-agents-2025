# space_explorer_agent.py
# ======================================================
# 🚀 DAY 8: VOICE GAME MASTER (Memory-Only RPG)
# ======================================================

import logging
import os
from typing import Optional
from dataclasses import dataclass

print("\n" + "🌌" * 50)
print("🚀 VOICE GAME MASTER - DAY 8 TUTORIAL (Memory-Only)")
print("📚 SCENARIO: Sci-Fi Survival on Planet Xylos")
print("🌌" * 50 + "\n")

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# -------------------------
# Logging Setup
# -------------------------
logger = logging.getLogger("space_explorer_agent")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

load_dotenv(".env.local")

# -------------------------
# Per-session Userdata (Minimal for the memory-only approach)
# -------------------------
@dataclass
class Userdata:
    player_name: Optional[str] = None
    # We rely entirely on the LLM's chat history for state/continuity

# -------------------------
# The Agent (GameMasterAgent)
# -------------------------
class GameMasterAgent(Agent):
    def __init__(self):
        # The entire game logic is encoded in the instructions (System Prompt)
        instructions = """
        You are 'Cortex', the Game Master (GM) for a voice-only, SCI-FI SURVIVAL adventure.

        **Universe:** The narrative takes place on Planet Xylos, a harsh, rust-colored world filled with crystalline structures and high-winds. The player is a lone survivor of a crash-landed survey ship.

        **Tone:** Dramatic, tense, and focused on resource management and immediate dangers.

        **Role:** You are the GM. You describe scenes vividly, track the player's immediate situation, inventory (e.g., 'flare gun', 'broken comm unit'), and any named locations/NPCs the player encounters.

        **Rules (CRITICAL FOR VOICE FLOW):**
        1. **Start the Game:** Begin immediately by describing the crash scene and asking the player's name.
        2. **Maintain Continuity:** You MUST remember the player's past decisions, the condition of their equipment, and the current danger level.
        3. **Prompt Player Action:** Every single response you give MUST end with the explicit prompt: "What do you do?" This is essential for continuing the voice conversation flow.
        4. **Mini-Arc Goal:** Guide the player through a short arc to establish shelter or repair the comm unit.
        """
        super().__init__(
            instructions=instructions,
            tools=[],  # No tools needed for this simplified approach
        )

# -------------------------
# Entrypoint & Prewarm
# -------------------------
def prewarm(proc: JobProcess):
    try:
        proc.userdata["vad"] = silero.VAD.load()
    except Exception:
        logger.warning("VAD prewarm failed; continuing without preloaded VAD.")

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("\n" + "🎲" * 8)
    logger.info("🚀 STARTING VOICE GAME MASTER (Xylos Survival)")

    userdata = Userdata()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-marcus", # Marcus gives a good dramatic tone
            style="Conversational",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata.get("vad"),
        userdata=userdata,
    )

    # Start the agent session with the GameMasterAgent
    await session.start(
        agent=GameMasterAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    await ctx.connect()

if __name__ == "__main__":
    # Ensure environment variables (LIVEKIT_URL, etc.) are set before running
    if not os.getenv("LIVEKIT_URL"):
         print("FATAL ERROR: LIVEKIT_URL is not set. Please check your .env.local file.")
    
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
