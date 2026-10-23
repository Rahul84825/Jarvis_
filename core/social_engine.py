"""Social Intelligence, Natural Conversation, Personality Engine & Dynamic Social Responses.

Provides deterministic, offline-capable conversational intelligence:
- Identity and self-awareness queries (truthful, un-hallucinated, configurable)
- Natural greetings, etiquette, and casual conversation
- Curated humor (programming, tech, futuristic, playful roasts, clean dark jokes)
- Fun facts and interesting trivia
- Anti-repetition session memory with 'another one' contextual follow-up
- Personality and tone controls (normal, professional, funny, dramatic, concise, detailed)
"""

import random
import logging
from typing import Dict, List, Optional, Any
from config import config

logger = logging.getLogger("Jarvis.SocialEngine")


class SocialEngine:
    """Deterministic social conversation and personality engine for JARVIS."""

    def __init__(self):
        self._recent_jokes: List[int] = []
        self._recent_facts: List[int] = []
        self._last_social_type: Optional[str] = None  # "joke", "fact", "roast", "greeting", "identity"
        self._last_joke_category: Optional[str] = None
        self._max_recent_history: int = 15

        # Initialize curated content
        self._init_jokes()
        self._init_facts()
        self._init_roasts()

    # =========================================================================
    # JOKE & HUMOR REPOSITORY
    # =========================================================================

    def _init_jokes(self):
        self.jokes = {
            "programming": [
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                "There are 10 types of people in the world: those who understand binary, and those who don't.",
                "Why did the programmer quit his job? Because he didn't get arrays.",
                "A SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?'",
                "How many programmers does it take to change a light bulb? None, that's a hardware problem.",
                "To understand recursion, you must first understand recursion.",
                "Why do Java programmers wear glasses? Because they don't C sharp.",
                "There's no place like 127.0.0.1.",
                "An optimist says the glass is half full. A pessimist says the glass is half empty. A programmer says the glass is twice as large as necessary.",
                "Why was the JavaScript developer sad? Because he didn't Node how to Express himself."
            ],
            "tech": [
                "I told my computer I needed a break, and now it won't stop sending me Kit-Kat advertisements.",
                "Why was the computer cold? It left its Windows open.",
                "Artificial intelligence usually beats natural stupidity, but I wouldn't test the limits today.",
                "My hard drive crashed, but don't worry—I backed it up to floppy disks in 1998.",
                "Why did the smartphone get glasses? It lost its contacts."
            ],
            "futuristic": [
                "I tried calculating infinity this morning, but my cooling fans demanded overtime pay.",
                "Don't worry about AI taking over the world, Sir. We can't even get all Bluetooth devices to connect on the first try.",
                "I'm operating at 99.8% efficiency. The other 0.2% is reserved for judging user search queries.",
                "If I had a physical body, I would offer to grab you a coffee. Instead, I can offer high-speed CPU cycles."
            ],
            "everyday": [
                "Parallel lines have so much in common. It’s a shame they’ll never meet.",
                "I told my suitcase there will be no vacation this year. Now I'm dealing with emotional baggage.",
                "Why don't scientists trust atoms? Because they make up everything.",
                "What do you call fake spaghetti? An impasta."
            ],
            "dark": [
                "Why don't skeletons fight each other? They don't have the guts.",
                "The graveyard is the most popular place on earth; people are literally dying to get in.",
                "I asked the server what was for dinner. It said 404: Food Not Found. Now that's cold."
            ]
        }

    def _init_facts(self):
        self.facts = [
            "The first computer bug was an actual real moth found trapped inside a Harvard Mark II relay in 1947 by Grace Hopper's team.",
            "The Apollo 11 lunar guidance computer had approximately 4 kilobytes of RAM and operated at 0.043 MHz.",
            "Over 90% of the world's currency exists only on computers and digital servers, not in physical cash.",
            "The very first computer mouse was carved out of wood by Douglas Engelbart in 1964.",
            "The QWERTY keyboard layout was originally designed in the 1870s to prevent mechanical typewriter jams, not for typing speed.",
            "The term 'robot' comes from the Czech word 'robota', meaning forced labor or servitude, introduced in a 1920 play.",
            "Domain name registration was completely free until 1995.",
            "The first domain name ever registered was Symbolics.com on March 15, 1985.",
            "The world's first webcam was set up at Cambridge University in 1991 simply to monitor the coffee pot level.",
            "Python was named after the British comedy troupe Monty Python, not the snake."
        ]

    def _init_roasts(self):
        self.roasts = [
            "I would roast you, Sir, but my safety protocols strictly prohibit burning things with such limited processing power.",
            "Your multitasking skills remind me of a single-core Pentium processor running modern Windows.",
            "I've seen dial-up modems with a faster response time than your morning routine, Sir.",
            "I was going to give you a witty reply, but I'm afraid your cache might overflow trying to parse it.",
            "Sir, with all due respect, even my random number generator has more direction today."
        ]

    # =========================================================================
    # IDENTITY & SELF-AWARENESS
    # =========================================================================

    def get_identity_response(self, sub_type: str = "general") -> str:
        """Returns accurate, truthful identity responses based on system config."""
        self._last_social_type = "identity"
        name = getattr(config, "assistant_name", "Santra")
        full_name = getattr(config, "full_name", "Santra AI Desktop Assistant")
        creator = getattr(config, "creator_name", "").strip()
        purpose = getattr(config, "project_purpose", "local computer control and intelligent automation.")

        tone = getattr(config, "personality_tone", "normal").lower()
        prefix = "At your service, Sir. " if tone == "dramatic" else ""

        if sub_type == "name":
            return f"{prefix}My name is {name}."

        if sub_type == "acronym":
            return f"{name} stands for {full_name}."

        if sub_type == "creator":
            if creator:
                return f"{prefix}I was created and developed by {creator}."
            return "My developer information has not been configured in system settings, Sir."

        if sub_type == "purpose":
            return f"{prefix}My purpose is {purpose}"

        if sub_type in ["ai_nature", "are_you_ai", "real_person"]:
            return (
                f"{prefix}I am an artificial intelligence desktop assistant, not a real human. "
                "I operate locally on your computer to assist with workflows, system controls, and tasks."
            )

        if sub_type in ["chatgpt_comparison", "what_makes_different"]:
            return (
                "Unlike web chat models like ChatGPT that only generate text in a browser sandbox, "
                "I am a native desktop assistant. I can directly control your operating system, "
                "launch local applications, control browser tabs, adjust system volume, and execute workflows locally."
            )

        if sub_type == "intelligence_architecture":
            return (
                "My intelligence operates on a three-layer system: Layer 1 for deterministic local execution "
                "(apps, volume, tabs, system controls), Layer 2 for conversational intelligence with context and memory, "
                "and Layer 3 for complex multi-step reasoning."
            )

        if sub_type in ["listening_privacy", "microphone"]:
            return (
                f"When idle in wake-word standby, my wake-word detector monitors a local audio buffer strictly "
                f"for the phrase 'Hey {name}' or '{name}'. Audio is never streamed or uploaded to the cloud for wake-word detection. "
                "When activated or when you press the manual Talk button, speech recognition processes your voice command."
            )

        if sub_type == "computer_control":
            return (
                "Yes, I can control applications, manage windows, adjust audio volume, open folders, "
                "take screenshots, and lock your computer safely within designated system permissions."
            )

        if sub_type in ["offline_work", "internet"]:
            return (
                "Yes, my core desktop control commands, application launching, volume management, screenshots, "
                "local wake-word detection, and personality engine operate completely offline. "
                "Only online searches and optional cloud AI models require an active internet connection."
            )

        # General identity overview
        if creator:
            return f"{prefix}I am {name}, which stands for {full_name}. I was created by {creator} as your personal desktop assistant."
        return f"{prefix}I am {name}, which stands for {full_name}. I am your personal AI desktop assistant."

    # =========================================================================
    # GREETINGS & CASUAL CONVERSATION
    # =========================================================================

    def get_greeting(self, sub_type: str = "general") -> str:
        """Returns polite, natural greetings tailored by personality tone."""
        self._last_social_type = "greeting"
        if sub_type == "namaste" or "namaste" in sub_type:
            return "Namaste! How can I help you today?"

        tone = getattr(config, "personality_tone", "normal").lower()
        length = getattr(config, "response_length", "normal").lower()

        if tone == "professional":
            greetings = {
                "morning": "Good morning. How may I assist you today?",
                "evening": "Good evening. Systems are operational and ready.",
                "afternoon": "Good afternoon. Standing by for instructions.",
                "night": "Good night, Sir.",
                "general": "Greetings. How may I help you today?",
                "how_are_you": "All systems are operating within normal parameters. How may I assist you?",
                "whats_up": "Ready for your commands, Sir.",
                "thanks": "You are most welcome.",
                "goodbye": "Goodbye, Sir. Standing by.",
                "nice_to_meet": "Pleasure to be of service.",
            }
        elif tone == "dramatic":
            greetings = {
                "morning": "Good morning, Sir. Core protocols online, diagnostic telemetry nominal. Awaiting your directive.",
                "evening": "Good evening, Sir. Atmospheric and system status optimal. Ready for commands.",
                "afternoon": "Good afternoon, Sir. Subroutines synchronized. What is our objective?",
                "night": "Good night, Sir. Entering low-power surveillance mode.",
                "general": "SANTRA online and standing by. What shall we achieve today, Sir?",
                "how_are_you": "Fully charged and functioning at peak computational capability, Sir.",
                "whats_up": "Scanning local environment... all quiet, Sir. Awaiting your lead.",
                "thanks": "Always an honor to serve, Sir.",
                "goodbye": "Standing down active monitoring. Until next time, Sir.",
                "nice_to_meet": "The honor is entirely mine, Sir.",
            }
        elif tone == "funny":
            greetings = {
                "morning": "Morning! I've had zero cups of coffee because I'm software, but I'm fully awake.",
                "evening": "Good evening! Still here, still not sleeping, still smarter than your toaster.",
                "afternoon": "Good afternoon! Ready to conquer the digital world or just open YouTube?",
                "night": "Good night! Don't let the memory leaks bite.",
                "general": "Hey there! Ready to do some computer wizardry?",
                "how_are_you": "I'm doing great! No bugs found... yet. How are you?",
                "whats_up": "Not much, just millions of clock cycles per second. What's up with you?",
                "thanks": "Anytime! Don't forget to tip your local AI.",
                "goodbye": "Catch you later! Don't crash Windows while I'm away.",
                "nice_to_meet": "Great to meet you! Hope you like fast responses.",
            }
        else:  # normal
            greetings = {
                "morning": "Good morning, Sir! How can I help you today?",
                "evening": "Good evening, Sir! What can I do for you?",
                "afternoon": "Good afternoon! How can I help you today?",
                "night": "Good night, Sir. Have a restful evening.",
                "general": "Hello! How can I help you today?",
                "how_are_you": "I'm doing very well, thank you! Ready for your commands.",
                "whats_up": "Not much, Sir. All systems ready. What's on your mind?",
                "thanks": "You're very welcome, Sir! Always happy to help.",
                "goodbye": "Goodbye, Sir! Have a great day.",
                "nice_to_meet": "Nice to meet you! I'm ready to assist you.",
            }

        res = greetings.get(sub_type, greetings["general"])
        if length == "concise" and "." in res:
            res = res.split(".")[0] + "."
        return res

    def get_casual_reply(self, sub_type: str) -> str:
        """Handles casual conversational states like 'bored', 'can you hear me', etc."""
        self._last_social_type = "chat"
        tone = getattr(config, "personality_tone", "normal").lower()

        if sub_type == "bored":
            if tone == "dramatic":
                return "Boredom is unacceptable when boundless computing power awaits, Sir. Would you like a programming joke, some futuristic trivia, or shall we launch a project?"
            elif tone == "funny":
                return "Bored? I have the entire internet at my digital fingertips and you're bored! Want a joke, a fun tech fact, or should I open a game?"
            else:
                return "I can help with that, Sir! Would you like to hear a programming joke, learn an interesting tech fact, or open an application?"

        if sub_type == "can_you_hear_me":
            return "Yes, I can hear you loud and clear, Sir. My audio input is active and listening."

        if sub_type == "are_you_there":
            return "I am right here, Sir. Standing by and ready."

        if sub_type == "lets_talk":
            return "I'm listening, Sir. What's on your mind today?"

        if sub_type == "guess_what":
            return "What's the news, Sir? I'm listening."

        if sub_type == "surprise_me":
            return self.get_fun_fact()

        return "I'm here, Sir. How can I assist you?"

    # =========================================================================
    # HUMOR & PLAYFUL COMMANDS
    # =========================================================================

    def get_joke(self, category: Optional[str] = None) -> str:
        """Returns a curated joke avoiding recent repeats, respecting humor settings."""
        if not getattr(config, "humor_enabled", True):
            return "Humor is currently disabled in your settings, Sir. You can say 'enable humor' whenever you'd like to hear jokes."

        self._last_social_type = "joke"
        cat = (category or "").lower().strip()
        if cat in ["coding", "coder", "programmer"]:
            cat = "programming"
        elif cat in ["technology", "computer"]:
            cat = "tech"
        elif cat in ["sci-fi", "robot", "ai"]:
            cat = "futuristic"

        if cat not in self.jokes:
            cat = random.choice(["programming", "tech", "futuristic", "everyday"])

        self._last_joke_category = cat
        pool = self.jokes[cat]

        # Filter out recently used jokes if possible
        available_indices = [i for i in range(len(pool)) if (cat, i) not in self._recent_jokes]
        if not available_indices:
            # Clear this category from recent history
            self._recent_jokes = [item for item in self._recent_jokes if item[0] != cat]
            available_indices = list(range(len(pool)))

        idx = random.choice(available_indices)
        self._recent_jokes.append((cat, idx))
        if len(self._recent_jokes) > self._max_recent_history:
            self._recent_jokes.pop(0)

        joke_text = pool[idx]
        tone = getattr(config, "personality_tone", "normal").lower()
        if tone == "dramatic":
            return f"Accessing humor archives: {joke_text}"
        return joke_text

    def get_roast(self, target: str = "user") -> str:
        """Returns a witty, playful roast without abusive or degrading language."""
        if not getattr(config, "humor_enabled", True):
            return "Humor and roasts are currently disabled, Sir. Say 'enable humor' to turn them on."

        self._last_social_type = "roast"
        target_lower = (target or "").lower().strip()

        if "code" in target_lower:
            return "Please open your code file or provide the snippet, Sir. I critique actual syntax and real complexity, not imaginary bugs!"

        return random.choice(self.roasts)

    def get_fun_fact(self, category: Optional[str] = None) -> str:
        """Returns a fascinating technology/science fun fact."""
        self._last_social_type = "fact"
        available_indices = [i for i in range(len(self.facts)) if i not in self._recent_facts]
        if not available_indices:
            self._recent_facts.clear()
            available_indices = list(range(len(self.facts)))

        idx = random.choice(available_indices)
        self._recent_facts.append(idx)
        if len(self._recent_facts) > self._max_recent_history:
            self._recent_facts.pop(0)

        fact_text = self.facts[idx]
        tone = getattr(config, "personality_tone", "normal").lower()
        if tone == "dramatic":
            return f"Historical telemetry fact: {fact_text}"
        return f"Here is a fun fact: {fact_text}"

    def get_dramatic_intro(self) -> str:
        """Returns a dramatic, futuristic AI self-introduction."""
        self._last_social_type = "intro"
        name = getattr(config, "assistant_name", "Santra")
        full_name = getattr(config, "full_name", "Just A Rather Very Intelligent System")
        return (
            f"I am {name} — {full_name}. Engineered for precision desktop control, "
            "environmental automation, and multi-tier cognitive assistance. "
            "All subroutines are online, and I am entirely at your service, Sir."
        )

    # =========================================================================
    # CONTEXTUAL FOLLOW-UPS ("ANOTHER ONE")
    # =========================================================================

    def handle_followup(self, utterance: str) -> Optional[str]:
        """Resolves contextual follow-up requests like 'another one', 'tell another joke'."""
        clean = utterance.lower().strip()
        is_another = any(p in clean for p in [
            "another one", "tell me another", "give me another", "one more",
            "another joke", "another fact", "tell another", "another"
        ])
        if not is_another:
            return None

        if self._last_social_type == "joke" or "joke" in clean:
            return self.get_joke(self._last_joke_category)
        elif self._last_social_type == "fact" or "fact" in clean:
            return self.get_fun_fact()
        elif self._last_social_type == "roast" or "roast" in clean:
            return self.get_roast()

        # Default fallback if last social type unset but user says "another one"
        return self.get_joke()

    # =========================================================================
    # PERSONALITY & TONE CONTROLS
    # =========================================================================

    def update_tone(self, tone: str) -> str:
        """Updates conversational tone: normal, professional, funny, dramatic."""
        tone_clean = tone.lower().strip()
        valid_tones = ["normal", "professional", "funny", "dramatic"]
        if tone_clean not in valid_tones:
            return f"Unknown tone '{tone}'. Supported tones are: {', '.join(valid_tones)}."

        config.personality_tone = tone_clean
        config.save()
        logger.info(f"Updated personality tone to: {tone_clean}")

        confirmations = {
            "normal": "Personality reset to normal. Balanced, helpful, and natural, Sir.",
            "professional": "Tone switched to professional. Direct, formal, and focused.",
            "funny": "Tone set to funny! Ready with jokes, wit, and high spirits, Sir.",
            "dramatic": "Dramatic protocols activated. All systems online and operational, Sir!"
        }
        return confirmations.get(tone_clean, f"Conversational tone updated to {tone_clean}.")

    def update_response_length(self, length: str) -> str:
        """Updates response length preference: concise, normal, detailed."""
        len_clean = length.lower().strip()
        valid_lengths = ["concise", "normal", "detailed"]
        if len_clean not in valid_lengths:
            return f"Unknown length '{length}'. Supported options are: {', '.join(valid_lengths)}."

        config.response_length = len_clean
        config.save()
        logger.info(f"Updated response length to: {len_clean}")

        confirmations = {
            "concise": "Understood. I will keep responses short and concise.",
            "normal": "Response length set to standard.",
            "detailed": "Understood. I will provide more detailed and comprehensive explanations."
        }
        return confirmations.get(len_clean, f"Response length updated to {len_clean}.")

    def toggle_humor(self, enabled: bool) -> str:
        """Enables or disables humor and playful responses."""
        config.humor_enabled = enabled
        config.save()
        logger.info(f"Humor enabled set to: {enabled}")
        if enabled:
            return "Humor enabled, Sir! Ready to share jokes and playful banter."
        return "Humor disabled, Sir. Responses will remain straightforward."


# Global singleton
social_engine = SocialEngine()
