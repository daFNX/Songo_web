import io
import math
import struct
import unittest
import wave

from index import AnalysisError, analyze_wav


def make_wav(bpm=120, duration=8, sample_rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        samples = bytearray()
        beat_interval = 60 / bpm
        for index in range(duration * sample_rate):
            time = index / sample_rate
            phase = time % beat_interval
            amplitude = 0.8 * math.exp(-phase * 35) if phase < 0.08 else 0.015
            value = int(32767 * amplitude * math.sin(2 * math.pi * 440 * time))
            samples.extend(struct.pack("<h", value))
        audio.writeframes(samples)
    return buffer.getvalue()


class AnalyzeWavTests(unittest.TestCase):
    def test_estimates_synthetic_120_bpm(self):
        result = analyze_wav(make_wav())
        self.assertEqual(result["bpm"], 120)

    def test_estimates_synthetic_90_bpm(self):
        result = analyze_wav(make_wav(bpm=90))
        self.assertEqual(result["bpm"], 90)

    def test_rejects_non_wav_input(self):
        with self.assertRaises(AnalysisError):
            analyze_wav(b"not a wav file")

    def test_rejects_silence(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(bytes(8000 * 4))
        with self.assertRaises(AnalysisError):
            analyze_wav(buffer.getvalue())

    def test_rejects_oversized_input(self):
        with self.assertRaises(AnalysisError) as error:
            analyze_wav(bytes(4 * 1024 * 1024 + 1))
        self.assertEqual(error.exception.status, 413)


if __name__ == "__main__":
    unittest.main()
