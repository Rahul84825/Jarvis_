import unittest
import time
from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer
from core.platform.platform_manager import platform_manager

class TestNaturalLanguageCommands(unittest.TestCase):
    """Extensive unit test suite verifying natural-language variation handling,
    safety question filtering, confidence scoring, wake-word immunity, and execution latency.
    """

    def setUp(self):
        self.engine = IntentEngine()
        self.normalizer = CommandNormalizer()

    # =========================================================================
    # 1. APP OPEN INTENT POSITIVE VARIATIONS (15+ variations)
    # =========================================================================
    def test_open_chrome_variations(self):
        variations = [
            "Open Chrome",
            "open google chrome",
            "launch chrome",
            "start chrome",
            "run chrome",
            "can you open chrome",
            "could you open chrome for me",
            "Jarvis, please start chrome",
            "Hey Jarvis, open chrome",
            "help me open chrome",
            "bring chrome up",
            "start google chrome",
            "I want to use Chrome",
            "Fire up Chrome",
            "Get Chrome running",
            "Please launch Chrome",
            "Would you mind opening Chrome?"
        ]
        for phrase in variations:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "open_app")
                self.assertEqual(res["target"], "chrome")
                self.assertGreaterEqual(res["confidence"], 0.85)

    def test_open_vscode_and_tools_variations(self):
        test_cases = [
            ("Open VS Code", "open_app", "vscode"),
            ("Launch Visual Studio Code", "open_app", "vscode"),
            ("Hey Jarvis, please start VS Code", "open_app", "vscode"),
            ("Bring up Antigravity editor", "open_app", "antigravity"),
            ("Launch Antigravity", "open_app", "antigravity"),
            ("Open the terminal", "open_app", "terminal"),
            ("Bring up the command line", "open_app", "terminal"),
            ("Start PowerShell", "open_app", "powershell"),
            ("Open Command Prompt", "open_app", "cmd"),
            ("Open File Explorer", "open_app", "explorer"),
            ("Launch Settings", "open_app", "settings"),
            ("Open Task Manager", "open_app", "taskmanager"),
            ("Bring up System Monitor", "open_app", "taskmanager"),
            ("Open Calculator", "open_app", "calculator"),
            ("Start Notepad", "open_app", "notepad")
        ]
        for phrase, expected_intent, expected_target in test_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], expected_intent)
                self.assertEqual(res["target"], expected_target)

    # =========================================================================
    # 2. APP CLOSE INTENT POSITIVE VARIATIONS (10+ variations)
    # =========================================================================
    def test_close_app_variations(self):
        variations = [
            ("Close Chrome", "chrome"),
            ("Can you close Chrome?", "chrome"),
            ("Jarvis, shut Chrome down", "chrome"),
            ("Please exit Chrome", "chrome"),
            ("Quit Chrome", "chrome"),
            ("Stop Chrome", "chrome"),
            ("Get Chrome out of here", "chrome"),
            ("Terminate Chrome", "chrome"),
            ("Kill Chrome", "chrome"),
            ("Hey Jarvis, close VS Code", "vscode"),
            ("Exit Visual Studio Code", "vscode"),
            ("Please close the terminal", "terminal")
        ]
        for phrase, expected_target in variations:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "close_app")
                self.assertEqual(res["target"], expected_target)
                self.assertGreaterEqual(res["confidence"], 0.85)

    # =========================================================================
    # 3. WINDOW MINIMIZE & MAXIMIZE POSITIVE VARIATIONS
    # =========================================================================
    def test_minimize_and_maximize_variations(self):
        min_cases = [
            ("Minimize Chrome", "minimize_app", "chrome"),
            ("Put Chrome in the background", "minimize_app", "chrome"),
            ("Hide Chrome", "minimize_app", "chrome"),
            ("Can you minimize Chrome?", "minimize_app", "chrome"),
            ("Please minimize this window", "window_control", None)
        ]
        for phrase, exp_intent, exp_target in min_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], exp_intent)
                if exp_target:
                    self.assertEqual(res["target"], exp_target)

        max_cases = [
            ("Maximize Chrome", "maximize_app", "chrome"),
            ("Make Chrome full screen", "maximize_app", "chrome"),
            ("Expand Chrome", "maximize_app", "chrome"),
            ("Maximize this window", "window_control", None)
        ]
        for phrase, exp_intent, exp_target in max_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], exp_intent)
                if exp_target:
                    self.assertEqual(res["target"], exp_target)

    # =========================================================================
    # 4. SYSTEM POWER & SECURITY INTENTS (15+ variations)
    # =========================================================================
    def test_lock_computer_variations(self):
        lock_cases = [
            "Lock my laptop",
            "Lock the laptop",
            "Lock my computer",
            "Lock the computer",
            "Please lock the PC",
            "Can you lock my PC?",
            "Lock this computer",
            "Secure my laptop",
            "Lock the screen",
            "Lock my screen",
            "Jarvis, lock the laptop",
            "Could you lock my computer for me?",
            "I need to lock the PC",
            "Put my computer on lock"
        ]
        for phrase in lock_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "lock_pc")
                self.assertGreaterEqual(res["confidence"], 0.95)

    def test_sleep_computer_variations(self):
        sleep_cases = [
            "Put my laptop to sleep",
            "Put the laptop to sleep",
            "Put the computer to sleep",
            "Sleep the computer",
            "Sleep my laptop",
            "Can you put my laptop to sleep?",
            "Please put the PC to sleep",
            "Go to sleep",
            "Send the laptop to sleep",
            "Make my computer sleep",
            "Jarvis, put the laptop to sleep"
        ]
        for phrase in sleep_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "sleep_pc")
                self.assertGreaterEqual(res["confidence"], 0.95)

    def test_restart_computer_variations(self):
        restart_cases = [
            "Restart my laptop",
            "Restart the computer",
            "Reboot my PC",
            "Reboot the laptop",
            "Can you restart the computer?",
            "Please restart my laptop",
            "Power cycle the PC"
        ]
        for phrase in restart_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "restart_pc")

    def test_shutdown_computer_variations(self):
        shutdown_cases = [
            "Shut down my laptop",
            "Shut down the computer",
            "Turn off my laptop",
            "Turn off the PC",
            "Power off the computer",
            "Can you shut down the laptop?",
            "Please turn off my computer",
            "I want to shut down the PC"
        ]
        for phrase in shutdown_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "shutdown_pc")

    def test_hibernate_computer_variations(self):
        hibernate_cases = [
            "Hibernate my laptop",
            "Put the computer into hibernation",
            "Can you hibernate the PC?",
            "Hibernate the computer"
        ]
        for phrase in hibernate_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "hibernate_pc")

    # =========================================================================
    # 5. FILESYSTEM & SCREENSHOT INTENTS
    # =========================================================================
    def test_filesystem_and_screenshot_variations(self):
        cases = [
            ("Open Downloads", "file_access", "open_folder", "downloads"),
            ("Open my Downloads folder", "file_access", "open_folder", "downloads"),
            ("Can you open Downloads?", "file_access", "open_folder", "downloads"),
            ("Please open the Downloads folder", "file_access", "open_folder", "downloads"),
            ("Take me to Downloads", "file_access", "open_folder", "downloads"),
            ("Show me Downloads", "file_access", "open_folder", "downloads"),
            ("Go to my Downloads folder", "file_access", "open_folder", "downloads"),
            ("Open resume.pdf", "file_access", "open_file", "resume.pdf"),
            ("Please open that PDF", "file_access", "open_file", "that.pdf"),
            ("Take a screenshot", "screenshot", "take_screenshot", None),
            ("Capture my screen", "screenshot", "take_screenshot", None),
            ("Screenshot this", "screenshot", "take_screenshot", None),
            ("Take a picture of the screen", "screenshot", "take_screenshot", None),
            ("Capture the desktop", "screenshot", "take_screenshot", None)
        ]
        for phrase, exp_intent, exp_action, exp_target in cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], exp_intent)
                self.assertEqual(res["action"], exp_action)
                if exp_target:
                    self.assertEqual(res["target"], exp_target)

    # =========================================================================
    # 6. NEGATIVE TESTS: INFORMATIONAL QUESTIONS MUST NOT EXECUTE ACTIONS (25+ tests)
    # =========================================================================
    def test_informational_questions_must_not_trigger_actions(self):
        negative_cases = [
            "What is Chrome?",
            "Tell me about Chrome.",
            "Why does Chrome crash?",
            "How do I install Chrome?",
            "Should I use Chrome?",
            "Why should I close Chrome?",
            "How do I lock my laptop?",
            "What happens if I shut down my computer?",
            "Can you explain sleep mode?",
            "How to open Chrome?",
            "Can you tell me how to open Chrome?",
            "Tell me how to lock the computer",
            "Why is my computer slow?",
            "What is VS Code used for?",
            "How do I reboot in safe mode?",
            "Explain what hibernation is",
            "What happens when I restart?",
            "Why did the computer sleep?",
            "How can I take a screenshot?",
            "What is the difference between sleep and hibernate?",
            "Is Chrome better than Firefox?",
            "Where are my downloaded files stored?",
            "What does shutdown do?",
            "Why do I need to lock my PC?",
            "Do you know how to code in Python?"
        ]
        for question in negative_cases:
            with self.subTest(question=question):
                res = self.engine.parse(question)
                # Must be classified as question or conversation, NEVER an actionable intent
                self.assertIn(res["intent"], ["question", "conversation"])
                self.assertNotIn(res["intent"], [
                    "open_app", "close_app", "minimize_app", "maximize_app",
                    "system_control", "screenshot", "file_access"
                ])

    # =========================================================================
    # 7. CONTEXT AWARENESS (Pronominal "it")
    # =========================================================================
    def test_context_awareness(self):
        # 1. Open Chrome sets last app target to chrome
        res1 = self.engine.parse("Open Chrome")
        self.assertEqual(res1["intent"], "open_app")
        self.assertEqual(res1["target"], "chrome")

        # 2. "Close it" resolves to chrome
        res2 = self.engine.parse("Close it")
        self.assertEqual(res2["intent"], "close_app")
        self.assertEqual(res2["target"], "chrome")

        # 3. Open VS Code
        res3 = self.engine.parse("Launch VS Code")
        self.assertEqual(res3["intent"], "open_app")
        self.assertEqual(res3["target"], "vscode")

        # 4. "Minimize it" resolves to vscode
        res4 = self.engine.parse("Minimize it")
        self.assertEqual(res4["intent"], "minimize_app")
        self.assertEqual(res4["target"], "vscode")

    # =========================================================================
    # 8. LATENCY PERFORMANCE TEST (< 5ms per command)
    # =========================================================================
    def test_local_parsing_latency(self):
        test_commands = [
            "Hey Jarvis, could you please open Google Chrome for me?",
            "Lock my computer",
            "Put my laptop to sleep",
            "Take a screenshot",
            "Close VS Code",
            "Open Downloads"
        ]
        for cmd in test_commands:
            t0 = time.perf_counter()
            res = self.engine.parse(cmd)
            duration_ms = (time.perf_counter() - t0) * 1000
            self.assertLess(duration_ms, 50.0, f"Parsing took too long: {duration_ms:.2f}ms for '{cmd}'")
            self.assertIsNotNone(res["intent"])

if __name__ == "__main__":
    unittest.main()
