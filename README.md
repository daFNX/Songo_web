# Songo

Songo estima los BPM de una grabación para ayudar a músicos a estudiar su propio material. Esta primera versión hace una sola cosa: recibe audio, estima el pulso y muestra el resultado.

- **Probar:** [songo-jet.vercel.app](https://songo-jet.vercel.app)
- **Código:** [github.com/daFNX/Songo_web](https://github.com/daFNX/Songo_web)

## Probarlo

No necesitas instalar nada: abre la aplicación, elige un audio y pulsa **Analizar tempo**. También puedes arrastrar el archivo a la zona de carga.

Se aceptan WAV, MP3, M4A, AAC, OGG, FLAC y algunos contenedores de audio/video, siempre que el navegador pueda decodificarlos. El límite del archivo original es **50 MB** y la duración máxima, **3 minutos**.

El original se decodifica en el navegador. Antes de enviarlo, Songo crea una versión mono WAV de 11.025 Hz: un minuto ocupa unos 1,3 MB, así que no hace falta recortar una canción WAV de 11 MB solo para probarla. La API recibe únicamente esa copia reducida; no almacena el archivo.

La decodificación depende del navegador y del códec instalado. Si un formato no se puede abrir, prueba a exportarlo como MP3 o WAV.

## Qué hace el análisis

Python valida el WAV compacto y estima los BPM a partir de cambios en la energía de la señal y autocorrelación. Es una aproximación inicial: las mitades o dobles del pulso, el silencio, una entrada débil y ritmos complejos pueden hacer que el resultado difiera del tempo musical.

Esta versión aún no detecta acordes ni tonalidad y no compara canciones. Una futura búsqueda de similitud requerirá una colección de referencia con derechos adecuados; una coincidencia, por sí sola, no demuestra plagio. Las letras y la sincronización con YouTube tampoco están implementadas.

## Seguridad y privacidad

- El audio original se procesa en el navegador; solo se envía la versión mono reducida.
- La API acepta WAV PCM, comprueba el contenido real y limita la petición a 4 MB.
- En servidor se acotan canales, frecuencia de muestreo y duración; los errores se devuelven como JSON.
- El backend no escribe el audio a disco, registra nombres de archivo ni usa servicios externos.
- El despliegue incluye CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`.

El análisis puede producir BPM incorrectos; no se debe interpretar como una identificación de canción ni como evidencia legal de plagio.

## Para ejecutar o probar cambios localmente

La ejecución local es opcional; la aplicación pública es la forma más sencilla de probar Songo. Para desarrollo se necesita Node.js 20+ y Python 3.10+:

```powershell
npm install
```

En una terminal:

```powershell
python api\analyze.py
```

En otra:

```powershell
npm run dev
```

Vite reenvía `/api` a Python en `127.0.0.1:8000`. Para comprobar los cambios:

```powershell
python -m unittest discover -s tests -p "test*.py"
npm run build
```

## Próximos pasos

1. Probar el estimador con grabaciones etiquetadas y mostrar cuándo la estimación es poco fiable.
2. Añadir acordes y tonalidad.
3. Investigar huellas musicales y similitud usando un catálogo autorizado.
4. Explorar letras y fuentes de reproducción con sus permisos y atribuciones correspondientes.
