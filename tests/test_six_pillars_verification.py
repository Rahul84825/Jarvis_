import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.persistent_memory import persistent_memory
from modules.web.web_intel import web_intel
from modules.communication.email_service import email_service
from modules.communication.chat_bridge import chat_bridge
from modules.devices.device_hub import device_hub
from core.ai.agent_brain import agent_brain
from core.proactive_daemon import proactive_daemon
from core.jarvis_runtime import JarvisRuntime

def run_tests():
    print("==================================================")
    print("       JARVIS 6 PILLARS & CORE INTEGRATION TEST   ")
    print("==================================================")

    # Test 1: Persistent Memory & Auto-Learning
    print("[TEST 1] Testing Persistent Long-Term Memory...")
    persistent_memory.set_preference("user_name", "Rahul")
    assert persistent_memory.get_preference("user_name") == "Rahul"
    learned = persistent_memory.auto_learn_from_speech("Remember that my favorite beverage is espresso")
    assert "favorite_beverage" in str(learned)
    print("  [PASS] Persistent Memory & Fact Auto-Learning.")

    # Test 2: Web Intelligence & News
    print("[TEST 2] Testing Web Intelligence & Live News...")
    weather = web_intel.get_weather("London")
    assert weather.get("success") is True or "formatted" in weather
    news = web_intel.get_live_news(category="world", limit=2)
    assert len(news) > 0
    print(f"  [PASS] Live News retrieved {len(news)} articles successfully.")

    # Test 3: Communication Suite
    print("[TEST 3] Testing Email & Chat Bridge...")
    emails = email_service.get_unread_emails(limit=2)
    assert len(emails) > 0
    tg = chat_bridge.send_telegram_message("Test ping")
    assert tg.get("success") is True
    print("  [PASS] Email & Chat Bridge functioning properly.")

    # Test 4: Device Hub & Smart Home
    print("[TEST 4] Testing Multi-Device & Smart Home Hub...")
    iot = device_hub.control_smart_device("light.living_room", "turn_on")
    assert iot.get("success") is True
    phone = device_hub.ping_phone()
    assert phone.get("success") is True
    print("  [PASS] Device Hub & Smart Home.")

    # Test 5: Autonomous ReAct AgentBrain
    print("[TEST 5] Testing Autonomous AgentBrain & Tool Calling...")
    res_briefing = agent_brain.reason_and_execute("Give me my morning briefing")
    assert len(res_briefing.get("text", "")) > 10
    print(f"  [PASS] Morning briefing generated: {res_briefing['text'][:60]}...")
    res_search = agent_brain.reason_and_execute("search web for quantum computing")
    assert len(res_search.get("text", "")) > 10
    print("  [PASS] Web Search Tool reasoning completed.")

    # Test 6: Voice Core Coordinator
    print("[TEST 6] Testing JarvisRuntime Coordinator...")
    runtime = JarvisRuntime()
    assert runtime.brain is not None
    assert runtime.listener is not None
    assert runtime.proactive_daemon is not None
    print("  [PASS] Jarvis Voice Core Coordinator initialized.")

    print("==================================================")
    print("  ALL 6 PILLARS & ARCHITECTURAL TESTS PASSED!     ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
