<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const MAX_FILE_BYTES = 50 * 1024 * 1024
const MAX_ANALYSIS_BYTES = 4 * 1024 * 1024
const MAX_DURATION_SECONDS = 180
const OUTPUT_SAMPLE_RATE = 11025
const SUPPORTED_EXTENSIONS = new Set(['wav', 'mp3', 'm4a', 'aac', 'ogg', 'flac', 'mp4', 'webm'])
const selectedFile = ref(null)
const isDragging = ref(false)
const isAnalyzing = ref(false)
const analysisStage = ref('preparing')
const result = ref(null)
const errorMessage = ref('')
const fileInput = ref(null)
let requestController

const fileSize = computed(() => {
  if (!selectedFile.value) return ''
  return selectedFile.value.size < 1024 * 1024
    ? `${(selectedFile.value.size / 1024).toFixed(0)} KB`
    : `${(selectedFile.value.size / 1024 / 1024).toFixed(1)} MB`
})

const fileFormat = computed(() => {
  if (!selectedFile.value) return ''
  return selectedFile.value.name.split('.').pop()?.toUpperCase() || 'AUDIO'
})

function validateFile(file) {
  if (!file) return 'No pudimos leer ese archivo. Inténtalo de nuevo.'
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (!SUPPORTED_EXTENSIONS.has(extension)) {
    return 'Prueba con WAV, MP3, M4A, AAC, OGG o FLAC. El formato debe ser compatible con tu navegador.'
  }
  if (file.size === 0) return 'El archivo está vacío. Elige una grabación con audio.'
  if (file.size > MAX_FILE_BYTES) {
    return 'El archivo supera el límite de 50 MB. Prueba con un fragmento más corto.'
  }
  return ''
}

function chooseFile(file) {
  errorMessage.value = ''
  result.value = null
  const validationError = validateFile(file)
  if (validationError) {
    selectedFile.value = null
    errorMessage.value = validationError
    return
  }
  selectedFile.value = file
}

function onInputChange(event) {
  chooseFile(event.target.files?.[0])
  event.target.value = ''
}

function onDrop(event) {
  isDragging.value = false
  chooseFile(event.dataTransfer?.files?.[0])
}

function formatDuration(seconds) {
  const minutes = Math.floor(seconds / 60)
  const remainder = Math.round(seconds % 60)
  return `${minutes}:${String(remainder).padStart(2, '0')}`
}

async function prepareAnalysisAudio(file) {
  const AudioContextConstructor = window.AudioContext || window.webkitAudioContext
  if (!AudioContextConstructor) {
    throw new Error('Este navegador no puede preparar el audio. Prueba con una versión reciente de Chrome, Edge o Safari.')
  }

  const audioContext = new AudioContextConstructor()
  let decodedAudio
  try {
    decodedAudio = await audioContext.decodeAudioData(await file.arrayBuffer())
  } catch {
    throw new Error('No pudimos leer ese audio. Prueba WAV, MP3, M4A u OGG compatible con tu navegador.')
  } finally {
    await audioContext.close()
  }

  if (decodedAudio.duration < 2) {
    throw new Error('El audio debe durar al menos 2 segundos.')
  }
  if (decodedAudio.duration > MAX_DURATION_SECONDS) {
    throw new Error('El audio supera la duración máxima de 3 minutos.')
  }

  const frameCount = Math.floor(decodedAudio.duration * OUTPUT_SAMPLE_RATE)
  const wav = new ArrayBuffer(44 + frameCount * 2)
  const header = new DataView(wav)
  const writeTag = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) {
      header.setUint8(offset + index, value.charCodeAt(index))
    }
  }

  writeTag(0, 'RIFF')
  header.setUint32(4, wav.byteLength - 8, true)
  writeTag(8, 'WAVE')
  writeTag(12, 'fmt ')
  header.setUint32(16, 16, true)
  header.setUint16(20, 1, true)
  header.setUint16(22, 1, true)
  header.setUint32(24, OUTPUT_SAMPLE_RATE, true)
  header.setUint32(28, OUTPUT_SAMPLE_RATE * 2, true)
  header.setUint16(32, 2, true)
  header.setUint16(34, 16, true)
  writeTag(36, 'data')
  header.setUint32(40, frameCount * 2, true)

  const channels = Array.from(
    { length: decodedAudio.numberOfChannels },
    (_, index) => decodedAudio.getChannelData(index),
  )
  const samplesPerOutputFrame = decodedAudio.sampleRate / OUTPUT_SAMPLE_RATE
  for (let index = 0; index < frameCount; index += 1) {
    const start = Math.floor(index * samplesPerOutputFrame)
    const end = Math.min(decodedAudio.length, Math.max(start + 1, Math.floor((index + 1) * samplesPerOutputFrame)))
    let sample = 0
    for (const channel of channels) {
      for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
        sample += channel[sourceIndex]
      }
    }
    sample /= (end - start) * channels.length
    const pcmSample = Math.max(-1, Math.min(1, sample))
    header.setInt16(44 + index * 2, pcmSample < 0 ? pcmSample * 32768 : pcmSample * 32767, true)
  }

  if (wav.byteLength > MAX_ANALYSIS_BYTES) {
    throw new Error('No pudimos reducir el audio a un tamaño compatible. Prueba con un fragmento más corto.')
  }
  return new Blob([wav], { type: 'audio/wav' })
}

async function analyze() {
  if (!selectedFile.value || isAnalyzing.value) return

  isAnalyzing.value = true
  errorMessage.value = ''
  result.value = null
  requestController = new AbortController()

  try {
    analysisStage.value = 'preparing'
    const analysisAudio = await prepareAnalysisAudio(selectedFile.value)
    analysisStage.value = 'analyzing'
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'audio/wav' },
      body: analysisAudio,
      signal: requestController.signal,
    })
    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.error || 'No pudimos analizar el archivo. Prueba con otro audio.')
    }
    result.value = {
      ...data,
      duration: formatDuration(data.duration_seconds),
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      errorMessage.value = error.message || 'No pudimos conectar con el analizador. Inténtalo de nuevo.'
    }
  } finally {
    isAnalyzing.value = false
    analysisStage.value = 'preparing'
    requestController = undefined
  }
}

function clearFile() {
  requestController?.abort()
  selectedFile.value = null
  result.value = null
  errorMessage.value = ''
  isAnalyzing.value = false
}

onBeforeUnmount(() => requestController?.abort())
</script>

<template>
  <div class="page-shell">
    <header class="topbar">
      <a class="wordmark" href="/" aria-label="Songo, inicio">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M5 17h4l3-8 5 15 4-11 2 4h4" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span>songo<span class="wordmark-period">.</span></span>
      </a>
      <div class="topbar-note"><span class="status-dot"></span> Estudio de audio · beta</div>
      <a class="topbar-link" href="#como-funciona">Cómo funciona <span aria-hidden="true">↗</span></a>
    </header>

    <main>
      <section class="intro" aria-labelledby="page-title">
        <div class="eyebrow"><span class="eyebrow-line"></span> PARA QUIENES HACEN MÚSICA</div>
        <h1 id="page-title">Encuentra el <span>pulso</span><br />de lo que creas.</h1>
        <p class="intro-copy">Sube una grabación y descubre su tempo en segundos.<br class="desktop-break" /> Tu música, sin dudas.</p>
      </section>

      <section class="workspace" aria-label="Analizador de tempo">
        <div class="section-heading">
          <div>
            <p class="section-index">01 <span>/</span> ANÁLISIS</p>
            <h2>Tu espacio de escucha</h2>
          </div>
          <span class="private-label"><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3.5" y="7" width="9" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg> Audio privado</span>
        </div>

        <div class="analysis-grid">
          <div class="upload-column">
            <div
              class="dropzone"
              :class="{ 'is-dragging': isDragging, 'has-file': selectedFile }"
              @dragenter.prevent="isDragging = true"
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @drop.prevent="onDrop"
            >
              <input
                ref="fileInput"
                class="visually-hidden"
                type="file"
                accept=".wav,.mp3,.m4a,.aac,.ogg,.flac,.mp4,.webm,audio/*"
                aria-label="Selecciona un archivo de audio"
                @change="onInputChange"
              />
              <template v-if="selectedFile">
                <div class="file-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M13.5 3.75H7.75a2 2 0 0 0-2 2v12.5a2 2 0 0 0 2 2h8.5a2 2 0 0 0 2-2V8.5l-4.75-4.75Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M13.5 4v4.5H18M8.5 13h7M8.5 16h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                </div>
                <div class="file-details">
                  <span class="file-name">{{ selectedFile.name }}</span>
                  <span class="file-meta">{{ fileSize }} <span>·</span> {{ fileFormat }}</span>
                </div>
                <button class="remove-file" type="button" aria-label="Quitar archivo" :disabled="isAnalyzing" @click="clearFile">×</button>
              </template>
              <template v-else>
                <div class="upload-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
                <p class="drop-title">Suelta tu audio aquí</p>
                <p class="drop-subtitle">o <button class="browse-button" type="button" @click="fileInput?.click()">explora tus archivos</button></p>
                <span class="file-requirements">WAV · MP3 · M4A · OGG · HASTA 50 MB</span>
              </template>
            </div>

            <p v-if="errorMessage" class="feedback error-message" role="alert">
              <span class="feedback-icon" aria-hidden="true">!</span>{{ errorMessage }}
            </p>
            <p v-else class="privacy-note"><span aria-hidden="true">✳</span> El original se queda en tu equipo; enviamos solo una copia ligera.</p>

            <button
              class="analyze-button"
              type="button"
              :disabled="!selectedFile || isAnalyzing"
              @click="analyze"
            >
              <span v-if="isAnalyzing" class="spinner" aria-hidden="true"></span>
              {{ isAnalyzing ? (analysisStage === 'preparing' ? 'Preparando el audio…' : 'Escuchando tu canción…') : 'Analizar tempo' }}
              <span v-if="!isAnalyzing" class="button-arrow" aria-hidden="true">↗</span>
            </button>
          </div>

          <div class="result-panel" aria-live="polite" aria-atomic="true">
            <div class="result-topline">
              <span class="result-label">TEMPO DETECTADO</span>
              <span v-if="result" class="result-tag"><span></span> ANÁLISIS LISTO</span>
              <span v-else-if="isAnalyzing" class="result-tag is-working"><span></span> EN PROCESO</span>
              <span v-else class="result-tag is-idle"><span></span> EN ESPERA</span>
            </div>
            <div v-if="result" class="bpm-reading">
              <span class="bpm-number">{{ result.bpm }}</span><span class="bpm-unit">BPM</span>
            </div>
            <div v-else class="bpm-placeholder">—<span>BPM</span></div>
            <p v-if="result" class="result-caption">Pulsos por minuto <span>·</span> {{ result.duration }}</p>
            <p v-else class="result-caption">Tu resultado aparecerá aquí</p>

            <div class="waveform" :class="{ 'waveform-active': result || isAnalyzing }" aria-hidden="true">
              <span v-for="(height, index) in [14, 23, 17, 31, 22, 42, 29, 50, 34, 61, 38, 49, 25, 57, 35, 68, 42, 55, 31, 47, 25, 59, 39, 71, 43, 56, 30, 48, 22, 62, 36, 52, 28, 44, 19, 35, 24]" :key="index" :class="height < 25 ? 'wave-short' : height < 46 ? 'wave-medium' : 'wave-tall'"></span>
            </div>

            <div v-if="result" class="result-footnote">
              <span class="result-footnote-mark">✳</span>
              <span>Estimación de tempo basada en el patrón rítmico de tu audio.</span>
            </div>
            <div v-else class="result-footnote">
              <span class="result-footnote-mark">✳</span>
              <span>Un primer paso para entender tu sonido.</span>
            </div>
          </div>
        </div>
      </section>

      <section id="como-funciona" class="how-it-works" aria-labelledby="how-title">
        <div class="how-heading">
          <p class="section-index">02 <span>/</span> EL PROCESO</p>
          <h2 id="how-title">Simple, como debería ser.</h2>
        </div>
        <div class="steps">
          <article class="step">
            <span class="step-number">01</span>
            <h3>Sube tu audio</h3>
            <p>Elige WAV, MP3, M4A u otro formato compatible. Hasta 50 MB.</p>
          </article>
          <article class="step">
            <span class="step-number">02</span>
            <h3>Analizamos el ritmo</h3>
            <p>Preparamos una copia ligera en tu navegador y Python estima el pulso.</p>
          </article>
          <article class="step">
            <span class="step-number">03</span>
            <h3>Encuentra tu tempo</h3>
            <p>Recibe una estimación de BPM para volver a crear con confianza.</p>
          </article>
        </div>
      </section>

      <section class="coming-soon" aria-label="Funciones futuras">
        <span class="coming-icon" aria-hidden="true">✳</span>
        <p><strong>Esto es solo el comienzo.</strong> Detección de acordes y análisis de similitud están en el horizonte.</p>
        <span class="coming-label">PRÓXIMAMENTE</span>
      </section>
    </main>

    <footer class="footer">
      <a class="footer-wordmark" href="/">songo<span>.</span></a>
      <span>Tu música, sin dudas.</span>
      <span class="footer-meta">Hecho para quienes hacen música <span aria-hidden="true">♡</span></span>
    </footer>
  </div>
</template>
