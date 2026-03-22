"""
AI Victim Chatbot Service — Phase 3
Multi-step conversational intake assistant that guides victims through
structured resource request creation using Groq-powered NLP.

Uses Groq API for intelligent intake extraction and conversation handling.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.services.distance import haversine

logger = logging.getLogger(__name__)

# ── Database client (lazy import to avoid initialization issues) ────────────────────
def _get_db():
    """Get database client, avoiding circular imports."""
    from app.database import db_admin
    return db_admin


# ── Conversation states ────────────────────────────────────────────────────────
class ConvState(StrEnum):
    GREETING = "greeting"
    ASK_SITUATION = "ask_situation"
    ASK_RESOURCE = "ask_resource"
    ASK_QUANTITY = "ask_quantity"
    ASK_LOCATION = "ask_location"
    ASK_PEOPLE = "ask_people"
    ASK_MEDICAL = "ask_medical"
    CONFIRM = "confirm"
    SUBMITTED = "submitted"


# ── Data models ────────────────────────────────────────────────────────────────
@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict | None = None


@dataclass
class ExtractedData:
    """Progressively built request data from conversation."""

    situation_description: str = ""
    resource_types: list[str] = field(default_factory=list)
    resource_type_scores: dict[str, float] = field(default_factory=dict)
    quantity: int = 1
    location: str = ""
    people_count: int = 1
    has_medical_needs: bool = False
    medical_details: str = ""
    disaster_type: str | None = None
    urgency_signals: list[dict] = field(default_factory=list)
    recommended_priority: str = "medium"
    priority_escalated: bool = False
    confidence: float = 0.5
    language_detected: str = "en"
    follow_up_question: str | None = None
    raw_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "situation_description": self.situation_description,
            "resource_types": self.resource_types,
            "resource_type_scores": self.resource_type_scores,
            "quantity": self.quantity,
            "location": self.location,
            "people_count": self.people_count,
            "has_medical_needs": self.has_medical_needs,
            "medical_details": self.medical_details,
            "disaster_type": self.disaster_type,
            "urgency_signals": self.urgency_signals,
            "recommended_priority": self.recommended_priority,
            "priority_escalated": self.priority_escalated,
            "confidence": self.confidence,
            "language_detected": self.language_detected,
            "follow_up_question": self.follow_up_question,
        }


@dataclass
class ChatSession:
    session_id: str
    state: ConvState = ConvState.GREETING
    messages: list[ChatMessage] = field(default_factory=list)
    extracted: ExtractedData = field(default_factory=ExtractedData)
    states_visited: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ── In-memory session store ────────────────────────────────────────────────────
_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str | None = None) -> ChatSession:
    """Return an existing session or create a new one."""
    if session_id and session_id in _sessions:
        return _sessions[session_id]
    new_id = session_id or str(uuid.uuid4())
    session = ChatSession(session_id=new_id)
    _sessions[new_id] = session
    return session


def delete_session(session_id: str) -> bool:
    """Remove a session from the store."""
    return _sessions.pop(session_id, None) is not None


def get_session_data(session_id: str) -> dict | None:
    """Return extracted data for a session, or None if not found."""
    session = _sessions.get(session_id)
    if not session:
        return None
    return session.extracted.to_dict()


# ── Groq intake extraction ─────────────────────────────────────────────────────

_INTAKE_EXTRACTION_PROMPT = """\
You are an emergency intake assistant. A person in distress has sent a message.
Extract structured data and return ONLY a valid JSON object:

{
  "situation_description": "<1-2 sentence neutral summary>",
  "resource_types": ["Food"|"Water"|"Medical"|"Shelter"|"Clothing"|"Evacuation"|"Volunteers"|"Financial Aid"|"Custom"],
  "quantity": <integer, default 1>,
  "location": "<address or landmark, null if not mentioned>",
  "people_count": <integer, default 1>,
  "has_medical_needs": <true|false>,
  "medical_details": "<description if true, else null>",
  "disaster_type": "<flood|fire|earthquake|storm|landslide|cyclone|drought|other|null>",
  "urgency_level": "<critical|high|medium|low>",
  "urgency_reason": "<one sentence explaining the urgency level>",
  "missing_info": ["location"|"quantity"|"resource_type"|"people_count"],
  "language_detected": "<ISO 639-1 code>",
  "response_to_user": "<ONE empathetic sentence + ONE question in the user's language
    to fill the most critical missing field. If all present, say:
    'Thank you — I have everything I need to submit your request.'>"
}

URGENCY RULES — set critical if message mentions: trapped, buried, unconscious,
not breathing, severe bleeding, drowning, fire spreading, building collapse,
no water >24h, medical emergency, pregnant woman in labor.
Set high for: multiple people in danger, elderly/children without shelter,
injuries without medical access.

RESOURCE RULES: resource_types is an array — include ALL implied types.
"hungry" → Food. "no clean water" → Water. "roof collapsed" → Shelter.
"hurt/bleeding" → Medical.

LANGUAGE RULE: response_to_user MUST be in the same language as the input.

STRICT: Return ONLY the JSON object. No preamble, no markdown fences.

User message:
"""

_URGENCY_TO_PRIORITY = {
    "critical": "critical", "high": "high", "medium": "medium", "low": "low",
}

# ── Resource keyword mappings (single definition) ──────────────────────────────
RESOURCE_KEYWORDS = {
    "Food": ["food", "foof", "eat", "hungry", "starving", "meal", "rice", "bread"],
    "Water": ["water", "watter", "drink", "thirsty", "thristy"],
    "Medical": ["medical", "medic", "doctor", "hospital", "hurt", "injured", "bleeding", "wound", "pain"],
    "Shelter": ["shelter", "home", "house", "tent", "roof", "sleep", "bed"],
    "Evacuation": ["evacuation", "evacuat", "rescue", "trapped", "stuck", "stranded", "pinned", "buried"],
}

DISASTER_RESOURCES = {
    "flood": ["Water", "Shelter", "Food", "Evacuation"],
    "earthquake": ["Shelter", "Medical", "Water", "Food"],
    "fire": ["Shelter", "Water", "Evacuation", "Medical"],
    "hurricane": ["Shelter", "Water", "Food", "Evacuation"],
    "cyclone": ["Shelter", "Water", "Food", "Evacuation"],
    "storm": ["Shelter", "Water", "Food"],
    "tsunami": ["Evacuation", "Shelter", "Water", "Medical"],
    "landslide": ["Evacuation", "Shelter", "Medical"],
    "drought": ["Water", "Food"],
    "tornado": ["Shelter", "Medical", "Water"],
}

TRAPPED_KEYWORDS = ["stuck", "trapped", "can't get out", "cannot get out", "cant leave", "stranded", "pinned", "buried"]


async def _extract_intake_via_llm(text: str) -> dict:
    """
    Call Groq for single-shot intake extraction.
    Raises RuntimeError on any failure — no silent fallback.
    """
    import json, os
    try:
        from groq import Groq
    except ImportError as exc:
        raise RuntimeError("groq package not installed. Run: pip install groq") from exc

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY env var is not set")

    client = Groq(api_key=api_key)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.chat.completions.create(
            model=os.environ.get("GROQ_INTAKE_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": _INTAKE_EXTRACTION_PROMPT + text}],
            max_tokens=600,
            temperature=0.0,
        ),
    )
    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)


def _detect_resources_from_keywords(text_lower: str) -> list[str]:
    """Detect resource types from keywords in text."""
    detected = []
    for resource_type, keywords in RESOURCE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(resource_type)
            if len(detected) >= 2:
                break
    return detected


def _detect_disaster_from_text(text_lower: str) -> tuple[str | None, list[str]]:
    """Detect disaster type and infer resources from text."""
    for disaster, resources in DISASTER_RESOURCES.items():
        if disaster in text_lower:
            return disaster, resources[:2]
    return None, []


def _determine_urgency(text_lower: str, is_trapped: bool) -> str:
    """Determine urgency level from text signals."""
    if is_trapped or any(word in text_lower for word in ["dying", "unconscious", "bleeding", "severe"]):
        return "critical"
    elif any(word in text_lower for word in ["urgent", "emergency", "help", "please"]):
        return "high"
    return "medium"


# ── Response templates ─────────────────────────────────────────────────────────
GREETING_MSG = (
    "🙏 **Hello! I'm your emergency assistance AI.**\n\n"
    "I'm here to help you request the resources you need. "
    "I'll ask a few quick questions to get help to you as fast as possible.\n\n"
    "**Please describe your current situation:**\n"
    "- What happened?\n"
    "- What do you need most urgently?\n"
    "- How many people are affected?\n\n"
    "_Tip: The more details you provide, the faster I can help you._"
)

RESOURCE_CONFIRM_TEMPLATE = (
    "✅ I've identified your need as: **{types}**\n\n"
    "Is this correct? If you need something different or additional, just tell me. "
    "Otherwise, say **yes** to continue."
)

RESOURCE_ASK = (
    "🤔 I need a bit more information to help you.\n\n"
    "**What do you need most urgently?**\n"
    "- 🍚 Food\n"
    "- 💧 Water\n"
    "- 🏥 Medical supplies\n"
    "- 🏠 Shelter\n"
    "- 👕 Clothing\n"
    "- 🚗 Evacuation\n"
    "- 🤝 Volunteers\n"
    "- 💰 Financial aid\n\n"
    "_You can also describe what you need in your own words._"
)

QUANTITY_ASK_TEMPLATE = (
    "📦 **How much {resource} do you need?**\n\n"
    "Please tell me:\n"
    "- The quantity (e.g., 10 bottles, 5 packs)\n"
    "- How many people this is for\n\n"
    "_Example: '10 water bottles for 5 people'_"
)

LOCATION_ASK = (
    "📍 **Where are you located?**\n\n"
    "Please provide as much detail as you can:\n"
    "- Full address\n"
    "- Neighborhood or landmark\n"
    "- Click the **Share GPS Location** button below\n\n"
    "_The more specific you are, the faster help can reach you._"
)

PEOPLE_ASK = (
    "👥 **How many people need help?**\n\n"
    "Please tell me:\n"
    "- Total number of people\n"
    "- Are there any children, elderly, or people with disabilities?\n"
    "- Any other vulnerable individuals?\n\n"
    "_This helps us prioritize your request appropriately._"
)

MEDICAL_ASK = (
    "🏥 **Does anyone have medical needs?**\n\n"
    "Please tell me if anyone:\n"
    "- Has injuries or wounds\n"
    "- Needs medication (insulin, inhaler, etc.)\n"
    "- Is pregnant or has chronic conditions\n"
    "- Needs immediate medical attention\n\n"
    "_If no medical needs, just say 'no' or 'none'._"
)

CONFIRM_TEMPLATE = (
    "📋 **Here's a summary of your request:**\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📝 **Situation:** {situation}\n"
    "📦 **Resource needed:** {resource}\n"
    "🔢 **Quantity:** {quantity}\n"
    "👥 **People affected:** {people}\n"
    "📍 **Location:** {location}\n"
    "🏥 **Medical needs:** {medical}\n"
    "⚡ **Priority level:** {priority}\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "**Does everything look correct?**\n"
    "- Say **yes** to submit your request\n"
    "- Say **no** to start over\n"
    "- Or tell me what needs to be changed"
)

SUBMITTED_MSG = (
    "✅ **Your request has been submitted successfully!**\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📋 A relief team will review your request shortly.\n"
    "📞 You may be contacted for verification.\n"
    "🔔 You'll receive updates as your request is processed.\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "**Important:**\n"
    "- Keep your phone charged and accessible\n"
    "- If your situation changes, start a new conversation\n"
    "- For life-threatening emergencies, call local emergency services\n\n"
    "_Stay safe. Help is on the way._ 🙏"
)

URGENT_FOLLOW_UP = (
    "⚠️ **I've detected this is a high-priority situation.**\n\n"
    "Your request has been marked as **{priority}** priority "
    "and will be escalated to emergency responders.\n\n"
    "Is there anything else you need to add before I submit?"
)

AREA_SUGGESTION_TEMPLATE = (
    "💡 **Smart Suggestion:** In your area, the most common requests are for:\n"
    "{resource_list}\n\n"
    "Is this what you need? Or do you need something different?"
)

DISASTER_CONTEXT_TEMPLATE = (
    "🌍 **Important:** There's an active **{disaster_type}** in your area.\n\n"
    "We've automatically increased your request priority. "
    "Emergency responders are already mobilized in your region.\n\n"
    "Please continue with your request details."
)


# ── Conversation engine ───────────────────────────────────────────────────────


def _detect_yes(text: str) -> bool:
    """Check if user is affirming."""
    text_lower = text.strip().lower()
    return bool(
        re.match(
            r"^(yes|yeah|yep|yup|correct|sure|ok|okay|y|confirm|right|that'?s? (right|correct))[\.\!\s]*$", text_lower
        )
    )


def _detect_no(text: str) -> bool:
    """Check if user is negating."""
    text_lower = text.strip().lower()
    return bool(re.match(r"^(no|nah|nope|wrong|incorrect|n|not really|start over|reset)[\.\!\s]*$", text_lower))


def _extract_number(text: str) -> int | None:
    """Pull the first integer from text."""
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def process_message(session_id: str | None, user_message: str) -> dict:
    """
    Process one user message in the conversation.
    Returns the chatbot response with metadata.
    """
    session = get_or_create_session(session_id)
    session.updated_at = datetime.now(UTC).isoformat()

    # Store user message
    session.messages.append(ChatMessage(role="user", content=user_message))
    session.extracted.raw_messages.append(user_message)

    # Run through the state machine
    response_text, metadata = _handle_state(session, user_message)

    # Store assistant message
    session.messages.append(ChatMessage(role="assistant", content=response_text, metadata=metadata))

    return {
        "session_id": session.session_id,
        "message": response_text,
        "state": session.state.value,
        "extracted_data": session.extracted.to_dict(),
        "metadata": metadata,
    }


def _handle_state(session: ChatSession, user_input: str) -> tuple[str, dict]:
    """Route user input through the conversation state machine."""

    # Track state transitions
    current_state = session.state.value
    if current_state not in session.states_visited:
        session.states_visited.append(current_state)

    # ── GREETING: first interaction ──
    if session.state == ConvState.GREETING:
        session.state = ConvState.ASK_SITUATION
        return GREETING_MSG, {"next_state": "ask_situation"}

    # ── ASK_SITUATION: user describes their situation ──
    elif session.state == ConvState.ASK_SITUATION:
        return _handle_situation(session, user_input)

    # ── ASK_RESOURCE: confirm or correct detected resource type ──
    elif session.state == ConvState.ASK_RESOURCE:
        return _handle_resource(session, user_input)

    # ── ASK_QUANTITY: how much / how many ──
    elif session.state == ConvState.ASK_QUANTITY:
        return _handle_quantity(session, user_input)

    # ── ASK_LOCATION: where are they ──
    elif session.state == ConvState.ASK_LOCATION:
        return _handle_location(session, user_input)

    # ── ASK_PEOPLE: group size & vulnerabilities ──
    elif session.state == ConvState.ASK_PEOPLE:
        return _handle_people(session, user_input)

    # ── ASK_MEDICAL: medical needs ──
    elif session.state == ConvState.ASK_MEDICAL:
        return _handle_medical(session, user_input)

    # ── CONFIRM: review and submit ──
    elif session.state == ConvState.CONFIRM:
        return _handle_confirm(session, user_input)

    # ── SUBMITTED: already done ──
    elif session.state == ConvState.SUBMITTED:
        return (
            "Your request has already been submitted. Start a new conversation if you need additional help.",
            {"already_submitted": True},
        )

    return "I'm sorry, something went wrong. Please try again.", {}


def _handle_situation(session: ChatSession, text: str) -> tuple[str, dict]:
    """Single-shot LLM intake via Groq with keyword fallback."""
    import asyncio, concurrent.futures

    session.extracted.situation_description = text
    text_lower = text.lower()
    llm_result: dict | None = None

    # Try Groq extraction first
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                llm_result = pool.submit(asyncio.run, _extract_intake_via_llm(text)).result(timeout=10)
        else:
            llm_result = loop.run_until_complete(_extract_intake_via_llm(text))
        logger.info("Groq extraction successful for session %s", session.session_id)
    except Exception as e:
        logger.warning("Groq intake extraction failed for session %s: %s — using keyword fallback", session.session_id, e)
        # Keyword-based fallback
        detected_disaster, disaster_resources = _detect_disaster_from_text(text_lower)
        detected_resources = _detect_resources_from_keywords(text_lower)
        is_trapped = any(word in text_lower for word in TRAPPED_KEYWORDS)
        
        if is_trapped and "Evacuation" not in detected_resources:
            detected_resources = ["Evacuation", "Shelter"]
        elif not detected_resources and detected_disaster:
            detected_resources = disaster_resources
        elif not detected_resources:
            detected_resources = ["Custom"]
        
        llm_result = {
            "situation_description": text[:200],
            "resource_types": detected_resources,
            "quantity": 1,
            "location": None,
            "people_count": 1,
            "has_medical_needs": any(kw in text_lower for kw in ["hurt", "injured", "bleeding", "medical", "doctor"]),
            "medical_details": "",
            "disaster_type": detected_disaster,
            "urgency_level": _determine_urgency(text_lower, is_trapped),
            "urgency_reason": "Keyword-based detection",
            "missing_info": ["location", "people_count"],
            "language_detected": "en",
            "response_to_user": None
        }

    # Apply extracted data to session
    d = session.extracted
    d.situation_description = llm_result.get("situation_description") or text
    d.resource_types = llm_result.get("resource_types") or []
    d.quantity = int(llm_result.get("quantity") or 1)
    d.location = llm_result.get("location") or ""
    d.people_count = int(llm_result.get("people_count") or 1)
    d.has_medical_needs = bool(llm_result.get("has_medical_needs", False))
    d.medical_details = llm_result.get("medical_details") or ""
    d.disaster_type = llm_result.get("disaster_type")
    d.language_detected = llm_result.get("language_detected", "en")
    d.follow_up_question = llm_result.get("response_to_user")
    d.recommended_priority = _URGENCY_TO_PRIORITY.get(
        llm_result.get("urgency_level", "medium"), "medium"
    )
    d.confidence = 0.85

    # ── POST-PROCESSING: Enhance detection ──
    if d.resource_types == ["Custom"] or not d.resource_types:
        d.resource_types = _detect_resources_from_keywords(text_lower)

    # Check for disaster types
    if not d.disaster_type:
        detected_disaster, disaster_resources = _detect_disaster_from_text(text_lower)
        if detected_disaster:
            d.disaster_type = detected_disaster
            if not d.resource_types or d.resource_types == ["Custom"]:
                d.resource_types = disaster_resources

    # Check for trapped situations
    is_trapped = any(word in text_lower for word in TRAPPED_KEYWORDS)
    if is_trapped:
        if not d.resource_types or d.resource_types == ["Custom"]:
            d.resource_types = ["Evacuation", "Shelter"]
        if d.recommended_priority not in ("critical", "high"):
            d.recommended_priority = "high"

    # Detect specific needs from remaining keywords
    if not d.resource_types or d.resource_types == ["Custom"]:
        if any(word in text_lower for word in ["hungry", "starving", "no food", "eat"]):
            d.resource_types = ["Food"]
        elif any(word in text_lower for word in ["thirsty", "no water", "dehydrat", "drink"]):
            d.resource_types = ["Water"]
        elif any(word in text_lower for word in ["hurt", "bleeding", "injured", "wound", "medical"]):
            d.resource_types = ["Medical"]
        elif any(word in text_lower for word in ["homeless", "no shelter", "roof", "house collapse"]):
            d.resource_types = ["Shelter"]

    if d.resource_types == ["Custom"]:
        d.resource_types = []

    # Add urgency message if priority is high or critical
    urgency_prefix = ""
    if d.recommended_priority in ("critical", "high"):
        urgency_prefix = URGENT_FOLLOW_UP.format(priority=d.recommended_priority.upper()) + "\n\n"

    missing = llm_result.get("missing_info", [])

    # Check for trapped situation specifically
    if is_trapped and not d.location:
        session.state = ConvState.ASK_LOCATION
        return (
            f"🚨 I understand you're **trapped and need rescue**. "
            f"I've marked this as **high priority** for evacuation.\n\n"
            f"**Where are you located?** Please provide your address, nearby landmark, or click the **Share GPS Location** button below.\n\n"
            f"_Emergency responders will be dispatched to your location._"
        ), {"extraction_method": "groq_enhanced", "trapped_detected": True, "gps_requested": True}

    all_present = (
        d.resource_types
        and d.location
        and "location" not in missing
        and "resource_type" not in missing
    )
    if all_present:
        session.state = ConvState.CONFIRM
        return urgency_prefix + _build_confirmation(session), {"extraction_method": "groq", "missing_info": missing}

    # Generate contextual response
    if d.resource_types:
        resource_str = ", ".join(d.resource_types[:3])
        if d.disaster_type:
            disaster_emoji = {
                "flood": "🌊", "earthquake": "🏚️", "fire": "🔥", "hurricane": "🌀",
                "cyclone": "🌀", "storm": "⛈️", "tsunami": "🌊", "landslide": "⛰️",
                "drought": "☀️", "tornado": "🌪️"
            }
            emoji = disaster_emoji.get(d.disaster_type, "🌍")
            response_text = (
                f"{emoji} I understand you're affected by a **{d.disaster_type}**. "
                f"I've noted you need **{resource_str}**.\n\n"
                f"**Where are you located?** This will help responders reach you faster.\n\n"
                f"Please provide your address, or click the **Share GPS Location** button below.\n\n"
                f"_Your request will be prioritized based on the {d.disaster_type} situation._"
            )
        else:
            response_text = (
                f"✅ I understand you need **{resource_str}**.\n\n"
                f"**Where are you located?** Please provide your address, nearby landmark, or click the **Share GPS Location** button below."
            )
    else:
        response_text = llm_result.get("response_to_user") or RESOURCE_ASK

    # Determine next state based on what's missing
    if not d.resource_types:
        session.state = ConvState.ASK_RESOURCE
    elif not d.location:
        session.state = ConvState.ASK_LOCATION
    elif d.people_count <= 1:
        session.state = ConvState.ASK_PEOPLE
    else:
        session.state = ConvState.ASK_MEDICAL if not d.has_medical_needs else ConvState.CONFIRM

    return urgency_prefix + response_text, {
        "extraction_method": "groq_enhanced",
        "missing_info": missing,
        "urgency_level": llm_result.get("urgency_level"),
        "language_detected": d.language_detected,
        "detected_disaster": d.disaster_type,
        "gps_requested": session.state == ConvState.ASK_LOCATION,
    }


def _handle_resource(session: ChatSession, text: str) -> tuple[str, dict]:
    """Handle resource type confirmation or correction via Groq."""
    import json, os

    if _detect_yes(text) and session.extracted.resource_types:
        primary = session.extracted.resource_types[0]
        session.state = ConvState.ASK_QUANTITY
        return QUANTITY_ASK_TEMPLATE.format(resource=primary), {}

    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        client = Groq(api_key=api_key)
        prompt = (
            "Classify the following text into one of these resource types: "
            "Food, Water, Medical, Shelter, Clothing, Evacuation, Volunteers, "
            "Financial Aid, Custom.\n"
            'Return ONLY a JSON object: {"resource_types": ["TypeName"], "confidence": 0.0-1.0}\n'
            f"Text: {text}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        parsed = json.loads(raw)
        types = parsed.get("resource_types", [])
        confidence = float(parsed.get("confidence", 0.0))
        if types and types != ["Custom"] and confidence >= 0.5:
            session.extracted.resource_types = types
            session.extracted.resource_type_scores = {t: confidence for t in types}
            primary = types[0]
            session.state = ConvState.ASK_QUANTITY
            return (
                f"Got it — I've updated your request to **{', '.join(types[:3])}**.\n\n"
                + QUANTITY_ASK_TEMPLATE.format(resource=primary)
            ), {"updated_types": types}
    except Exception as e:
        logger.error(f"Groq resource classification failed: {e}")

    return (
        "I'm not sure what resource type that is. Could you pick one from this list?\n\n"
        "- Food\n- Water\n- Medical\n- Shelter\n- Clothing\n- Evacuation\n"
        "- Volunteers\n- Financial Aid"
    ), {"retry": True}


def _handle_quantity(session: ChatSession, text: str) -> tuple[str, dict]:
    """Extract quantity from user response."""
    qty = _extract_number(text)
    if qty:
        session.extracted.quantity = min(qty, 9999)

    # Also check for people count in this answer
    people_match = re.search(r"(\d+)\s*(people|persons?|family members?|of us)", text.lower())
    if people_match:
        session.extracted.people_count = int(people_match.group(1))

    session.state = ConvState.ASK_LOCATION
    return LOCATION_ASK, {"quantity_detected": session.extracted.quantity, "gps_requested": True}


def _handle_location(session: ChatSession, text: str) -> tuple[str, dict]:
    """Store location information or request GPS if unknown."""
    text_lower = text.strip().lower()

    # Check if user doesn't know their location
    dont_know_patterns = [
        "don't know", "dont know", "not sure", "unsure", "no idea",
        "i don't know", "i dont know", "unknown", "can't tell", "cant tell"
    ]

    if any(pattern in text_lower for pattern in dont_know_patterns):
        # Request GPS from frontend
        session.extracted.location = "GPS_PENDING"
        session.state = ConvState.ASK_PEOPLE
        return (
            "📍 **No problem! We can use your GPS location.**\n\n"
            "Please allow location access on your device, or provide any details you can:\n"
            "- Nearby landmarks\n"
            "- Street name\n"
            "- City or neighborhood\n"
            "- Any description of your surroundings\n\n"
            "_If you can't provide any details, we'll use your device's GPS automatically._"
        ), {"gps_requested": True}

    # Store the location
    session.extracted.location = text.strip()
    session.state = ConvState.ASK_PEOPLE
    return PEOPLE_ASK, {"location_stored": True}


def _handle_people(session: ChatSession, text: str) -> tuple[str, dict]:
    """Extract people count. Priority/urgency already set by Groq intake."""
    qty = _extract_number(text)
    if qty:
        session.extracted.people_count = qty

    if session.extracted.has_medical_needs:
        session.state = ConvState.CONFIRM
        return _build_confirmation(session), {"skipped_medical_ask": True}

    session.state = ConvState.ASK_MEDICAL
    return MEDICAL_ASK, {}


def _handle_medical(session: ChatSession, text: str) -> tuple[str, dict]:
    """Process medical needs. No local NLP — urgency set by Groq intake."""
    if _detect_no(text):
        session.extracted.has_medical_needs = False
    else:
        session.extracted.has_medical_needs = True
        session.extracted.medical_details = text
        if session.extracted.recommended_priority not in ("critical", "high"):
            session.extracted.recommended_priority = "high"
            session.extracted.priority_escalated = True

    session.state = ConvState.CONFIRM
    return _build_confirmation(session), {}


def _build_confirmation(session: ChatSession) -> str:
    """Build the confirmation summary message."""
    d = session.extracted
    resource_str = ", ".join(d.resource_types) if d.resource_types else "Not determined"
    medical_str = d.medical_details if d.has_medical_needs else "None reported"
    priority_str = d.recommended_priority.upper()
    if d.priority_escalated:
        priority_str += " (auto-escalated due to urgency signals)"

    # Format location for display
    location_display = d.location or "Not provided"
    if location_display == "GPS_PENDING":
        location_display = "📍 GPS Location (will be captured automatically)"

    return CONFIRM_TEMPLATE.format(
        situation=d.situation_description[:200] or "Not provided",
        resource=resource_str,
        quantity=d.quantity,
        people=d.people_count,
        location=location_display,
        medical=medical_str,
        priority=priority_str,
    )


def _handle_confirm(session: ChatSession, text: str) -> tuple[str, dict]:
    """Handle confirmation response."""
    if _detect_yes(text):
        session.state = ConvState.SUBMITTED
        # Track final state
        if ConvState.CONFIRM.value not in session.states_visited:
            session.states_visited.append(ConvState.CONFIRM.value)
        if ConvState.SUBMITTED.value not in session.states_visited:
            session.states_visited.append(ConvState.SUBMITTED.value)

        # Log the completed session
        final_resource = session.extracted.resource_types[0] if session.extracted.resource_types else None
        final_priority = session.extracted.recommended_priority

        # Run async logging in sync context using asyncio.run (or fire-and-forget)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,  # Will be set when user authentication is integrated
                        states_visited=session.states_visited,
                        final_resource_type=final_resource,
                        final_priority=final_priority,
                        completion_status="completed"
                    )
                )
            else:
                loop.run_until_complete(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=final_resource,
                        final_priority=final_priority,
                        completion_status="completed"
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to log completed session: {e}")

        return SUBMITTED_MSG, {
            "submitted": True,
            "extracted_data": session.extracted.to_dict(),
        }
    elif _detect_no(text):
        # Reset to start - log as abandoned
        if ConvState.CONFIRM.value not in session.states_visited:
            session.states_visited.append(ConvState.CONFIRM.value)

        # Log abandoned session
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=None,
                        final_priority=None,
                        completion_status="abandoned"
                    )
                )
            else:
                loop.run_until_complete(
                    log_chatbot_session(
                        session_id=session.session_id,
                        user_id=None,
                        states_visited=session.states_visited,
                        final_resource_type=None,
                        final_priority=None,
                        completion_status="abandoned"
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to log abandoned session: {e}")

        session.state = ConvState.ASK_SITUATION
        session.extracted = ExtractedData()
        return (
            "No problem! Let's start over.\n\n"
            "**Can you describe your current situation?** "
            "What happened and what do you need?"
        ), {"reset": True}
    else:
        return ("Please confirm by saying **yes** to submit your request, or **no** to start over."), {
            "awaiting_confirmation": True
        }


# ── Smart Defaults & Urgency Context Services ─────────────────────────────────────


@dataclass
class SmartDefaultsResult:
    """Result of get_smart_defaults query."""
    top_resource_types: list[str]
    area_message: str
    has_data: bool


@dataclass
class UrgencyContextResult:
    """Result of get_urgency_context check."""
    has_active_disaster: bool
    disaster_type: str | None
    disaster_title: str | None
    priority_boost: int
    urgency_message: str | None


async def get_smart_defaults(user_location: tuple[float, float]) -> SmartDefaultsResult:
    """
    Query resource_requests from the last 30 days where latitude/longitude
    is within 50km of user_location. Return the top 3 most requested types.

    Args:
        user_location: Tuple of (latitude, longitude)

    Returns:
        SmartDefaultsResult with top resource types and a message for the user
    """
    from datetime import timedelta

    user_lat, user_lon = user_location
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    try:
        db = _get_db()
        response = await db.table("resource_requests").select(
            "id, resource_type, latitude, longitude, created_at"
        ).gte("created_at", thirty_days_ago).execute()

        requests = response.data or []
        if not requests:
            return SmartDefaultsResult(
                top_resource_types=[],
                area_message="",
                has_data=False
            )

        # Count resource types within 50km
        type_counts: dict[str, int] = {}
        for req in requests:
            req_lat = req.get("latitude")
            req_lon = req.get("longitude")
            if req_lat is None or req_lon is None:
                continue

            distance = haversine(user_lat, user_lon, req_lat, req_lon)
            if distance <= 50:  # Within 50km
                resource_type = req.get("resource_type", "unknown")
                if resource_type:
                    type_counts[resource_type] = type_counts.get(resource_type, 0) + 1

        if not type_counts:
            return SmartDefaultsResult(
                top_resource_types=[],
                area_message="",
                has_data=False
            )

        # Get top 3 most requested types
        sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        top_3 = [t[0] for t in sorted_types[:3]]

        # Build user-friendly message
        if top_3:
            if len(top_3) == 1:
                area_message = f"In your area, most people are requesting {top_3[0]}. Is that what you need too?"
            elif len(top_3) == 2:
                area_message = f"In your area, most people are requesting {top_3[0]} and {top_3[1]}. Is either of these what you need?"
            else:
                area_message = f"In your area, most people are requesting {top_3[0]}, {top_3[1]}, or {top_3[2]}. Is any of these what you need?"
        else:
            area_message = ""

        return SmartDefaultsResult(
            top_resource_types=top_3,
            area_message=area_message,
            has_data=True
        )

    except Exception as e:
        logger.warning(f"Error getting smart defaults: {e}")
        return SmartDefaultsResult(
            top_resource_types=[],
            area_message="",
            has_data=False
        )


async def get_urgency_context(user_location: tuple[float, float]) -> UrgencyContextResult:
    """
    Check for any active (status='active') disaster within 100km of user_location.
    If found, auto-boost priority by 1 level and inform the user.

    Args:
        user_location: Tuple of (latitude, longitude)

    Returns:
        UrgencyContextResult with disaster info and priority boost
    """
    user_lat, user_lon = user_location

    try:
        db = _get_db()
        response = await db.table("disasters").select(
            "id, type, title, status, location_id"
        ).eq("status", "active").execute()

        disasters = response.data or []
        if not disasters:
            return UrgencyContextResult(
                has_active_disaster=False,
                disaster_type=None,
                disaster_title=None,
                priority_boost=0,
                urgency_message=None
            )

        # Need to get location data for each disaster to calculate distance
        location_ids = [d.get("location_id") for d in disasters if d.get("location_id")]
        location_map = {}

        if location_ids:
            loc_response = await db.table("locations").select(
                "id, latitude, longitude"
            ).in_("id", location_ids).execute()
            for loc in loc_response.data or []:
                location_map[loc["id"]] = loc

        # Check each disaster within 100km
        for disaster in disasters:
            location_id = disaster.get("location_id")
            if not location_id or location_id not in location_map:
                continue

            loc = location_map[location_id]
            disaster_lat = loc.get("latitude")
            disaster_lon = loc.get("longitude")

            if disaster_lat is None or disaster_lon is None:
                continue

            distance = haversine(user_lat, user_lon, disaster_lat, disaster_lon)

            if distance <= 100:  # Within 100km
                disaster_type = disaster.get("type", "disaster")
                disaster_title = disaster.get("title", "")

                return UrgencyContextResult(
                    has_active_disaster=True,
                    disaster_type=disaster_type,
                    disaster_title=disaster_title,
                    priority_boost=1,
                    urgency_message=f"There's an active {disaster_type} near you. We've marked your request as high priority."
                )

        return UrgencyContextResult(
            has_active_disaster=False,
            disaster_type=None,
            disaster_title=None,
            priority_boost=0,
            urgency_message=None
        )

    except Exception as e:
        logger.warning(f"Error getting urgency context: {e}")
        return UrgencyContextResult(
            has_active_disaster=False,
            disaster_type=None,
            disaster_title=None,
            priority_boost=0,
            urgency_message=None
        )


async def log_chatbot_session(
    session_id: str,
    user_id: str | None,
    states_visited: list[str],
    final_resource_type: str | None,
    final_priority: str | None,
    completion_status: str
) -> bool:
    """
    Log a completed chatbot session to the chatbot_sessions table.

    Args:
        session_id: The unique session identifier
        user_id: The user ID if authenticated
        states_visited: List of conversation states visited
        final_resource_type: The resource type selected
        final_priority: The priority of the request
        completion_status: 'completed' or 'abandoned'

    Returns:
        True if logged successfully, False otherwise
    """
    try:
        db = _get_db()
        insert_data = {
            "session_id": session_id,
            "user_id": user_id,
            "states_visited": states_visited,
            "final_resource_type": final_resource_type,
            "final_priority": final_priority,
            "completion_status": completion_status,
        }

        await db.table("chatbot_sessions").insert(insert_data).execute()
        logger.info(f"Logged chatbot session {session_id} as {completion_status}")
        return True

    except Exception as e:
        logger.error(f"Error logging chatbot session {session_id}: {e}")
        return False