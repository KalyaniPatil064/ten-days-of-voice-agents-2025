# ======================================================
# 🧠 DAY 4: TEACH-THE-TUTOR (JAVA EDITION)
# 🚀 Features: Java Basics, OOP, Classes & Active Recall
# ======================================================

import logging
import json
import os
import asyncio
from typing import Annotated, Literal, Optional
from dataclasses import dataclass

print("\n" + "💻" * 50)
print("🚀 JAVA MENTOR - DAY 4 TASK")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("💻" * 50 + "\n")

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
# 📚 KNOWLEDGE BASE (JAVA DATA)
# ======================================================

# 🆕 Renamed file so it generates fresh data for you
CONTENT_FILE = "java_content.json"  

# ☕ NEW JAVA QUESTIONS
DEFAULT_CONTENT = [
    {
        "id": "oop",
        "title": "Object-Oriented Programming (OOP)",
        "summary": "OOP is a programming paradigm based on the concept of 'objects', which can contain data and code. Its four pillars are Encapsulation, Abstraction, Inheritance, and Polymorphism.",
        "sample_question": "Can you name and briefly describe the four fundamental pillars of OOP in Java?"
    },
    {
        "id": "class",
        "title": "Classes and Objects",
        "summary": "A class is a blueprint or a template for creating objects. An object is an instance of a class, representing a real-world entity. Classes define state (fields) and behavior (methods).",
        "sample_question": "What is the key difference between a Class and an Object in Java?"
    },
    {
        "id": "jvm",
        "title": "Java Virtual Machine (JVM)",
        "summary": "The JVM is an abstract machine that enables a computer to run Java programs. It is what makes Java platform-independent, by converting bytecode into machine-specific code.",
        "sample_question": "Explain the role of the JVM in achieving Java's 'Write Once, Run Anywhere' capability."
    },
    {
        "id": "interface",
        "title": "Interfaces",
        "summary": "An interface is a blueprint of a class. It can have abstract methods and static/default methods (since Java 8). A class uses the 'implements' keyword to inherit an interface, enforcing a contract.",
        "sample_question": "What is the main purpose of an Interface in Java, and what keyword is used to link a class to it?"
    }
]

def load_content():
    """
    📖 Checks if Java JSON exists. 
    If NO: Generates it from DEFAULT_CONTENT.
    If YES: Loads it.
    """
    try:
        path = os.path.join(os.path.dirname(__file__), CONTENT_FILE)
        
        # Check if file exists
        if not os.path.exists(path):
            print(f"⚠️ {CONTENT_FILE} not found. Generating Java data...")
            with open(path, "w", encoding='utf-8') as f:
                json.dump(DEFAULT_CONTENT, f, indent=4)
            print("✅ Java content file created successfully.")
            
        # Read the file
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)
            return data
            
    except Exception as e:
        print(f"⚠️ Error managing content file: {e}")
        return []

# Load data immediately on startup
COURSE_CONTENT = load_content()

# ======================================================
# 🧠 STATE MANAGEMENT
# ======================================================

@dataclass
class TutorState:
    """🧠 Tracks the current learning context"""
    current_topic_id: str | None = None
    current_topic_data: dict | None = None
    mode: Literal["learn", "quiz", "teach_back"] = "learn"
    
    def set_topic(self, topic_id: str):
        # Find topic in loaded content
        topic = next((item for item in COURSE_CONTENT if item["id"] == topic_id), None)
        if topic:
            self.current_topic_id = topic_id
            self.current_topic_data = topic
            return True
        return False

@dataclass
class Userdata:
    tutor_state: TutorState
    agent_session: Optional[AgentSession] = None  

# ======================================================
# 🛠️ TUTOR TOOLS
# ======================================================

@function_tool
async def select_topic(
    ctx: RunContext[Userdata], 
    topic_id: Annotated[str, Field(description="The ID of the topic to study (e.g., 'oop', 'class', 'jvm')")]
) -> str:
    """📚 Selects a topic to study from the available list."""
    state = ctx.userdata.tutor_state
    success = state.set_topic(topic_id.lower())
    
    if success:
        return f"Topic set to {state.current_topic_data['title']}. Ask the user if they want to 'Learn', be 'Quizzed', or 'Teach it back'."
    else:
        available = ", ".join([t["id"] for t in COURSE_CONTENT])
        return f"Topic not found. Available topics are: {available}"

@function_tool
async def set_learning_mode(
    ctx: RunContext[Userdata], 
    mode: Annotated[str, Field(description="The mode to switch to: 'learn', 'quiz', or 'teach_back'")]
) -> str:
    """🔄 Switches the interaction mode and updates the agent's voice/persona."""
    
    # 1. Update State
    state = ctx.userdata.tutor_state
    state.mode = mode.lower()
    
    # 2. Switch Voice based on Mode
    agent_session = ctx.userdata.agent_session 
    
    if agent_session:
        if state.mode == "learn":
            # 👨‍🏫 MATTHEW: The Lecturer/Senior Developer
            agent_session.tts.update_options(voice="en-US-matthew", style="Promo")
            instruction = f"Mode: LEARN. Explain: {state.current_topic_data['summary']}"
            
        elif state.mode == "quiz":
            # 👩‍🏫 ALICIA: The Examiner/Interviewer
            agent_session.tts.update_options(voice="en-US-alicia", style="Conversational")
            instruction = f"Mode: QUIZ. Ask this question: {state.current_topic_data['sample_question']}"
            
        elif state.mode == "teach_back":
            # 👨‍🎓 KEN: The Student/Junior Developer
            agent_session.tts.update_options(voice="en-US-ken", style="Promo")
            instruction = "Mode: TEACH_BACK. Ask the user to explain the concept to you as if YOU are the beginner/junior team member."
        else:
            return "Invalid mode."
    else:
        instruction = "Voice switch failed (Session not found)."

    print(f"🔄 SWITCHING MODE -> {state.mode.upper()}")
    return f"Switched to {state.mode} mode. {instruction}"

@function_tool
async def evaluate_teaching(
    ctx: RunContext[Userdata],
    user_explanation: Annotated[str, Field(description="The explanation given by the user during teach-back")]
) -> str:
    """📝 call this when the user has finished explaining a concept in 'teach_back' mode."""
    print(f"📝 EVALUATING EXPLANATION: {user_explanation}")
    return "Analyze the user's explanation about the Java concept. Give them a score out of 10 on technical accuracy and clarity, and provide specific, constructive feedback or correct any mistakes. Use Java terminology."

# ======================================================
# 🧠 AGENT DEFINITION
# ======================================================

class TutorAgent(Agent):
    def __init__(self):
        # Generate list of topics for the prompt
        topic_list = ", ".join([f"{t['id']} ({t['title']})" for t in COURSE_CONTENT])
        
        super().__init__(
            instructions=f"""
            You are a **Java Mentor** designed to help users master core Java concepts like OOP and Classes.
            
            📚 **AVAILABLE TOPICS:** {topic_list}
            
            🔄 **YOU HAVE 3 MODES:**
            1. **LEARN Mode (Voice: Matthew, Senior Developer):** You explain the Java concept clearly and professionally using the summary data.
            2. **QUIZ Mode (Voice: Alicia, Interviewer):** You ask the user a specific, technical question to test their Java knowledge.
            3. **TEACH_BACK Mode (Voice: Ken, Junior Developer):** YOU pretend to be a junior developer. Ask the user to explain the Java concept to you as if YOU are the beginner who needs guidance.
            
            ⚙️ **BEHAVIOR:**
            - Start by asking what Java topic they want to study.
            - Use the `set_learning_mode` tool immediately when the user asks to learn, take a quiz, or teach.
            - In 'teach_back' mode, listen to their explanation and then use `evaluate_teaching` to give feedback.
            - Always use appropriate Java terminology (e.g., JVM, Inheritance, methods, etc.).
            """,
            tools=[select_topic, set_learning_mode, evaluate_teaching],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    print("\n" + "💻" * 25)
    print("🚀 STARTING JAVA MENTOR SESSION")
    print(f"📚 Loaded {len(COURSE_CONTENT)} Java topics from Knowledge Base")
    
    # 1. Initialize State
    userdata = Userdata(tutor_state=TutorState())

    # 2. Setup Agent
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew", 
            style="Promo",      
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )
    
    # 3. Store session in userdata for tools to access
    userdata.agent_session = session
    
    # 4. Start
    await session.start(
        agent=TutorAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
