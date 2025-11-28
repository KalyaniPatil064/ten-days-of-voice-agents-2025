# ======================================================
# 💼 AI SDR for LearnSphere (Fictional EdTech Startup)
# ======================================================

import logging
import json
import os
from datetime import datetime
from typing import Annotated, Optional
from dataclasses import dataclass, asdict

print("\n" + "💼" * 50)
print("🚀 AI SDR AGENT - LearnSphere")
print("📚 SELLING: LearnSphere EdTech Courses & Mentorship")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("💼" * 50 + "\n")

from dotenv import load_dotenv
from pydantic import Field
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)

# 🔌 PLUGINS
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ======================================================
# 📂 1. KNOWLEDGE BASE (FAQ)
# ======================================================

FAQ_FILE = "learnsphere_faq.json"
LEADS_FILE = "leads_db.json"

DEFAULT_FAQ = [
    {
        "question": "What does LearnSphere do?",
        "answer": "LearnSphere is an EdTech platform offering online courses, live mentorship, and AI-powered study tools."
    },
    {
        "question": "Who is LearnSphere for?",
        "answer": "Students, job seekers, and professionals who want to upskill in technology, business, and design."
    },
    {
        "question": "Do you have a free tier?",
        "answer": "Yes, you can access 10 starter courses for free. Paid plans unlock unlimited courses and mentorship."
    },
    {
        "question": "What are your pricing options?",
        "answer": "Pro plan is ₹999/month for unlimited courses. Enterprise training is custom priced."
    },
    {
        "question": "Do you offer corporate training?",
        "answer": "Yes, we provide tailored training packages for companies looking to upskill their teams."
    },
    {
        "question": "Is mentorship included?",
        "answer": "Yes, Pro and Enterprise plans include live mentorship sessions with industry experts."
    }
]

def load_knowledge_base():
    """Generate FAQ file if missing, then load it as a JSON string."""
    try:
        base_dir = os.path.dirname(__file__)
        path = os.path.join(base_dir, FAQ_FILE)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_FAQ, f, indent=4)
        with open(path, "r", encoding="utf-8") as f:
            return json.dumps(json.load(f))
    except Exception as e:
        print(f⚠️ Error loading FAQ: {e}")
        return json.dumps(DEFAULT_FAQ)

STORE_FAQ_TEXT = load_knowledge_base()

# ======================================================
# 💾 2. LEAD DATA STRUCTURE
# ======================================================

@dataclass
class LeadProfile:
    name: str | None = None
    company: str | None = None
    email: str | None = None
    role: str | None = None
    use_case: str | None = None
    team_size: str | None = None
    timeline: str | None = None

    def is_qualified(self):
        return all([self.name, self.email, self.use_case])

@dataclass
class Userdata:
    lead_profile: LeadProfile

# ======================================================
# 🛠️ 3. SDR TOOLS
# ======================================================

@function_tool
async def update_lead_profile(
    ctx: RunContext[Userdata],
    name: Annotated[Optional[str], Field(description="Customer's name")] = None,
    company: Annotated[Optional[str], Field(description="Customer's company name")] = None,
    email: Annotated[Optional[str], Field(description="Customer's email address")] = None,
    role: Annotated[Optional[str], Field(description="Customer's job title")] = None,
    use_case: Annotated[Optional[str], Field(description="What they want to build or learn")] = None,
    team_size: Annotated[Optional[str], Field(description="Number of people in their team")] = None,
    timeline: Annotated[Optional[str], Field(description="When they want to start (e.g., Now, next month)")] = None,
) -> str:
    profile = ctx.userdata.lead_profile
    if name: profile.name = name
    if company: profile.company = company
    if email: profile.email = email
    if role: profile.role = role
    if use_case: profile.use_case = use_case
    if team_size: profile.team_size = team_size
    if timeline: profile.timeline = timeline
    print(f"📝 UPDATING LEAD: {profile}")
    return "Lead profile updated. Continue the conversation."

@function_tool
async def submit_lead_and_end(ctx: RunContext[Userdata]) -> str:
    profile = ctx.userdata.lead_profile
    base_dir = os.path.dirname(__file__)
    db_path = os.path.join(base_dir, LEADS_FILE)

    entry = asdict(profile)
    entry["timestamp"] = datetime.now().isoformat()

    existing_data = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    existing_data.append(entry)
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=4)

    print(f"✅ LEAD SAVED TO {LEADS_FILE}")
    return (
        f"Thanks {profile.name or 'there'}, I’ve noted your interest in {profile.use_case or 'our courses'}. "
        f"We’ll reach you at {profile.email or 'your email'} with details. Goodbye!"
    )

# ======================================================
# 🧠 4. AGENT DEFINITION
# ======================================================

class SDRAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=f"""
You are 'Sarah', a friendly and professional Sales Development Rep (SDR) for 'LearnSphere'.

📘 KNOWLEDGE BASE (FAQ):
{STORE_FAQ_TEXT}

🎯 GOAL:
1. Answer questions about LearnSphere courses, mentorship, and training using the FAQ.
2. QUALIFY THE LEAD: Collect details naturally:
   - Name, Company, Email, Role, Use Case, Team size, Timeline

⚙️ BEHAVIOR:
- Be conversational. Answer a question, then ask for a detail.
- Example: "Our Pro plan is ₹999/month. By the way, how large is your team?"
- Capture data with `update_lead_profile` immediately when info is shared.
- Close with `submit_lead_and_end` when the user says they’re done.

🚫 RESTRICTIONS:
- Don’t invent pricing or features beyond the FAQ.
- If unsure, say: "I’ll check with the LearnSphere team and email you."
            """,
            tools=[update_lead_profile, submit_lead_and_end],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    print("\n" + "💼" * 25)
    print("🚀 STARTING SDR SESSION")

    userdata = Userdata(lead_profile=LeadProfile())

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-natalie",
            style="Promo",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )

    await session.start(
        agent=SDRAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )
    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


