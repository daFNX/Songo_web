import io
import json
import math
import struct
import unittest
import wave

from api.analyze import AnalysisError, analyze_wav, application


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


def request_api(method, path, body=b"", content_type=""):
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": io.BytesIO(body),
    }
    response = {}

    def start_response(status, headers):
        response["status"] = int(status.split(" ", 1)[0])
        response["headers"] = dict(headers)

    payload = b"".join(application(environ, start_response))
    return response["status"], response["headers"], json.loads(payload)


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

    def test_wsgi_health_route(self):
        status, headers, payload = request_api("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_wsgi_analyze_route_returns_bpm(self):
        status, _, payload = request_api("POST", "/api/analyze", make_wav(), "audio/wav")
        self.assertEqual(status, 200)
        self.assertEqual(payload["bpm"], 120)

    def test_wsgi_rejects_unsupported_content_type(self):
        status, _, payload = request_api("POST", "/api/analyze", b"invalid", "text/plain")
        self.assertEqual(status, 415)
        self.assertIn("WAV", payload["error"])

    def test_wsgi_rejects_oversized_request_before_reading_body(self):
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/api/analyze",
            "CONTENT_LENGTH": str(4 * 1024 * 1024 + 1),
            "CONTENT_TYPE": "audio/wav",
            "wsgi.input": io.BytesIO(b""),
        }
        response = {}

        def start_response(status, headers):
            response["status"] = int(status.split(" ", 1)[0])

        payload = b"".join(application(environ, start_response))
        self.assertEqual(response["status"], 413)
        self.assertIn("4 MB", json.loads(payload)["error"])


if __name__ == "__main__":
    unittest.main()
