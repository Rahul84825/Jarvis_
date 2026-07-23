import unittest
from memory.session_memory import SessionMemory

class TestSessionMemory(unittest.TestCase):
    def test_add_and_retrieve_interaction(self):
        """Verifies that interactions can be added and retrieved correctly."""
        memory = SessionMemory(max_turns=5)
        memory.add_interaction("Hello Jarvis", "Hello! How can I assist you today?")
        
        self.assertEqual(len(memory.history), 1)
        self.assertEqual(memory.history[0]["user"], "Hello Jarvis")
        self.assertEqual(memory.history[0]["assistant"], "Hello! How can I assist you today?")

    def test_trimming_limit(self):
        """Verifies that the FIFO trimming works when maximum turns are reached."""
        max_turns = 3
        memory = SessionMemory(max_turns=max_turns)
        
        # Add 4 interactions
        for i in range(1, 5):
            memory.add_interaction(f"User query {i}", f"Jarvis response {i}")
            
        self.assertEqual(len(memory.history), max_turns)
        # The oldest one (1) should have been popped, history starts at 2
        self.assertEqual(memory.history[0]["user"], "User query 2")
        self.assertEqual(memory.history[-1]["user"], "User query 4")

    def test_get_gemini_history_format(self):
        """Verifies that history is formatted correctly for Google Gemini API."""
        memory = SessionMemory(max_turns=5)
        memory.add_interaction("Hi", "Hello")
        memory.add_interaction("Weather?", "It is sunny.")
        
        gemini_hist = memory.get_gemini_history()
        
        expected = [
            {"role": "user", "parts": ["Hi"]},
            {"role": "model", "parts": ["Hello"]},
            {"role": "user", "parts": ["Weather?"]},
            {"role": "model", "parts": ["It is sunny."]}
        ]
        self.assertEqual(gemini_hist, expected)

    def test_clear_memory(self):
        """Verifies that clearing memory removes all entries."""
        memory = SessionMemory(max_turns=5)
        memory.add_interaction("Hi", "Hello")
        self.assertEqual(len(memory.history), 1)
        
        memory.clear()
        self.assertEqual(len(memory.history), 0)

if __name__ == "__main__":
    unittest.main()
