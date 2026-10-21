import io
import json
import math
import os
import struct
import wave
from http import HTTPStatus
from wsgiref.simple_server import make_server

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_DURATION_SECONDS = 180
ANALYSIS_RATE = 100


class AnalysisError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def decode_samples(frames, sample_width, channels):
    if sample_width not in (1, 2, 3, 4):
        raise AnalysisError("Este WAV usa una profundidad de audio no compatible.")

    samples_per_channel = len(frames) // (sample_width * channels)
    mono = []
    for frame_index in range(samples_per_channel):
        total = 0.0
        for channel in range(channels):
            start = (frame_index * channels + channel) * sample_width
            chunk = frames[start : start + sample_width]
            if sample_width == 1:
                value = (chunk[0] - 128) / 128.0
            elif sample_width == 2:
                value = struct.unpack("<h", chunk)[0] / 32768.0
            elif sample_width == 3:
                integer = int.from_bytes(chunk, "little", signed=False)
                if integer & 0x800000:
                    integer -= 1 << 24
                value = integer / 8388608.0
            else:
                value = struct.unpack("<i", chunk)[0] / 2147483648.0
            total += value
        mono.append(total / channels)
    return mono


def estimate_bpm(samples, sample_rate):
    window_size = max(1, sample_rate // ANALYSIS_RATE)
    envelope = []
    for start in range(0, len(samples), window_size):
        block = samples[start : start + window_size]
        if block:
            envelope.append(math.sqrt(sum(value * value for value in block) / len(block)))

    if len(envelope) < ANALYSIS_RATE * 2 or max(envelope, default=0) < 0.002:
        raise AnalysisError("No encontramos suficiente señal de audio para estimar el tempo.")

    onset = [max(0.0, envelope[index] - envelope[index - 1]) for index in range(1, len(envelope))]
    onset_mean = sum(onset) / len(onset)
    onset = [max(0.0, value - onset_mean) for value in onset]
    energy = sum(value * value for value in onset)
    if energy < 1e-8:
        raise AnalysisError("No detectamos pulsos claros. Prueba con otro fragmento de audio.")

    min_lag = max(1, round(60 * ANALYSIS_RATE / 200))
    max_lag = min(round(60 * ANALYSIS_RATE / 40), len(onset) // 2)
    candidates = []
    for lag in range(min_lag, max_lag + 1):
        left = onset[:-lag]
        right = onset[lag:]
        left_energy = sum(value * value for value in left)
        right_energy = sum(value * value for value in right)
        if left_energy and right_energy:
            correlation = sum(a * b for a, b in zip(left, right))
            score = correlation / math.sqrt(left_energy * right_energy)
            candidates.append((score, lag))

    if not candidates:
        raise AnalysisError("El fragmento es demasiado corto para estimar el tempo.")

    best_score = max(candidate[0] for candidate in candidates)
    _, lag = min(
        (candidate for candidate in candidates if candidate[0] >= best_score - 1e-6),
        key=lambda candidate: candidate[1],
    )
    bpm = round(60 * ANALYSIS_RATE / lag)
    return bpm


def analyze_wav(content):
    if not content:
        raise AnalysisError("El archivo está vacío.")
    if len(content) > MAX_FILE_BYTES:
        raise AnalysisError("El archivo supera el límite de 4 MB.", 413)

    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            channels = audio.getnchannels()
            sample_rate = audio.getframerate()
            sample_width = audio.getsampwidth()
            frame_count = audio.getnframes()
            duration = frame_count / sample_rate if sample_rate else 0

            if channels not in (1, 2):
                raise AnalysisError("El WAV debe tener uno o dos canales de audio.")
            if sample_rate < 8000 or sample_rate > 96000:
                raise AnalysisError("La frecuencia de muestreo WAV no es compatible.")
            if duration < 2:
                raise AnalysisError("El audio debe durar al menos 2 segundos.")
            if duration > MAX_DURATION_SECONDS:
                raise AnalysisError("El audio supera la duración máxima de 3 minutos.")
            samples = decode_samples(audio.readframes(frame_count), sample_width, channels)
    except AnalysisError:
        raise
    except (wave.Error, EOFError, struct.error, ZeroDivisionError):
        raise AnalysisError("El archivo no es un WAV PCM válido o está dañado.")

    bpm = estimate_bpm(samples, sample_rate)
    return {
        "bpm": bpm,
        "duration_seconds": round(duration, 1),
        "message": "Tempo estimado. El resultado es orientativo.",
    }


def respond(start_response, status, payload, extra_headers=()):
    body = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
    ]
    headers.extend(extra_headers)
    start_response(f"{status} {HTTPStatus(status).phrase}", headers)
    return [body]


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "")

    if method == "GET" and path == "/api/health":
        return respond(start_response, 200, {"status": "ok"})
    if method != "POST":
        return respond(
            start_response,
            405,
            {"error": "Método no permitido."},
            [("Allow", "GET, POST")],
        )
    if path != "/api/analyze":
        return respond(start_response, 404, {"error": "Ruta no encontrada."})

    content_type = environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower()
    if content_type not in ("audio/wav", "audio/x-wav", "application/octet-stream"):
        return respond(start_response, 415, {"error": "Formato no compatible. Sube un archivo WAV."})

    try:
        content_length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        return respond(start_response, 400, {"error": "No pudimos validar el tamaño del archivo."})

    if content_length <= 0:
        return respond(start_response, 400, {"error": "No recibimos ningún archivo."})
    if content_length > MAX_FILE_BYTES:
        return respond(start_response, 413, {"error": "El archivo supera el límite de 4 MB."})

    content = environ["wsgi.input"].read(content_length)
    if len(content) != content_length:
        return respond(start_response, 400, {"error": "La carga del archivo quedó incompleta."})

    try:
        return respond(start_response, 200, analyze_wav(content))
    except AnalysisError as error:
        return respond(start_response, error.status, {"error": str(error)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Songo API escuchando en http://127.0.0.1:{port}")
    make_server("127.0.0.1", port, application).serve_forever()
