import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.transcriber import SpeechTranscriber

class TestSpeechTranscriber(unittest.TestCase):
    @patch('faster_whisper.WhisperModel')
    def test_lazy_loading(self, mock_whisper_model):
        """Verifies that the Whisper model is loaded only when transcription is requested."""
        transcriber = SpeechTranscriber(model_size="tiny", device="cpu")
        self.assertIsNone(transcriber._model)
        
        # Call private load method
        transcriber._load_model()
        self.assertIsNotNone(transcriber._model)
        mock_whisper_model.assert_called_once_with("tiny", device="cpu", compute_type="int8")

    @patch('pathlib.Path.exists')
    @patch('faster_whisper.WhisperModel')
    def test_transcription_success(self, mock_whisper_model, mock_exists):
        """Verifies that transcription successfully aggregates segments and returns clean text."""
        mock_exists.return_value = True
        
        # Create dummy segment objects
        segment1 = MagicMock()
        segment1.text = "Hello"
        segment2 = MagicMock()
        segment2.text = "this is Jarvis."
        
        # Create dummy info object
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.99
        info.duration = 2.5
        
        # Setup model mock
        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([segment1, segment2], info)
        mock_whisper_model.return_value = mock_model_instance
        
        transcriber = SpeechTranscriber(model_size="base", device="cpu")
        text = transcriber.transcribe("dummy_file.wav")
        
        # Assertions
        self.assertEqual(text, "Hello this is Jarvis.")
        initial_prompt = "Jarvis, open VS Code, YouTube, Chrome, Spotify, Notepad, Calculator, lock computer, take a screenshot, calculate, system status, shutdown, restart, volume up, volume down, mute, unmute, minimize, maximize, what time is it, what is the date, search google, play music."
        mock_model_instance.transcribe.assert_called_once_with(
            "dummy_file.wav",
            beam_size=5,
            language="en",
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            vad_filter=False
        )

    @patch('pathlib.Path.exists')
    @patch('faster_whisper.WhisperModel')
    def test_phonetic_replacements(self, mock_whisper_model, mock_exists):
        """Verifies that common speech misrecognitions are corrected."""
        mock_exists.return_value = True
        segment = MagicMock()
        segment.text = "Open vee es code and you tube"
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.99
        info.duration = 2.5

        mock_model_instance = MagicMock()
        mock_model_instance.transcribe.return_value = ([segment], info)
        mock_whisper_model.return_value = mock_model_instance

        transcriber = SpeechTranscriber(model_size="base", device="cpu")
        text = transcriber.transcribe("dummy_file.wav")
        self.assertEqual(text, "Open VS Code and YouTube")

    def test_missing_audio_file(self):
        """Verifies that FileNotFoundError is raised if audio file does not exist."""
        transcriber = SpeechTranscriber(model_size="base", device="cpu")
        transcriber._model = MagicMock() # bypass loading
        
        with self.assertRaises(FileNotFoundError):
            transcriber.transcribe("non_existent_file.wav")

if __name__ == "__main__":
    unittest.main()
