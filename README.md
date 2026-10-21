# Songo

**Tu música, sin dudas.** Maqueta funcional para estimar el tempo de grabaciones musicales.

## Qué incluye esta versión

- Interfaz en Vue 3 y Vite, adaptada a móviles y escritorio.
- Estimación de BPM en Python mediante análisis local de la envolvente de energía y autocorrelación.
- API WSGI de la biblioteca estándar, compatible con el runtime Python de Vercel y ejecutable localmente.
- Carga por selector o arrastrar y soltar; por ahora, solo WAV PCM de 1 o 2 canales.
- Errores visibles para formatos incorrectos, archivos vacíos/dañados/silenciosos, audios demasiado cortos o largos y archivos mayores de 4 MB.
- La API procesa el audio en memoria y no lo guarda.

El BPM es una **estimación experimental**, no una medición profesional. La cifra de confianza también es orientativa. Aún no se detectan acordes, tonalidad ni canciones coincidentes. La detección de similitud y cualquier evaluación de plagio necesitan un corpus autorizado, pruebas y revisión humana: una coincidencia no demuestra plagio. Las letras y la reproducción de YouTube tampoco forman parte de esta maqueta.

## Requisitos

- Node.js 20 o posterior y npm.
- Python 3.10 o posterior.
- Sin dependencias Python externas.

## Ejecutar localmente

En una terminal:

```powershell
npm install
```

Terminal 1, iniciar la API Python:

```powershell
python api\analyze.py
```

Terminal 2, iniciar Vue:

```powershell
npm run dev
```

Abre la URL local que indique Vite. Vite reenvía `/api` a Python en `127.0.0.1:8000`.

## Verificar

```powershell
python -m unittest discover -s api -p "test*.py"
npm run build
```

## Publicar en Vercel

La configuración `vercel.json` sirve la aplicación Vite y dirige `/api/analyze` a la función Python, en el mismo origen. Desde una cuenta con Vercel CLI configurado:

```powershell
npx vercel
```

Para producción:

```powershell
npx vercel --prod
```

La plataforma impone límites de tamaño y tiempo a las funciones. Esta maqueta limita la carga a 4 MB y la duración a 3 minutos; usa WAV PCM, que ocupa bastante espacio, por lo que es práctico analizar fragmentos breves.

## Medidas de seguridad incluidas

- Lista permitida de formato y validación real del contenedor WAV en Python; la extensión o el MIME del navegador no bastan para confiar en el contenido.
- Límite de bytes comprobado en navegador y servidor antes de analizar.
- Límites de canales, frecuencia de muestreo y duración para acotar trabajo y memoria.
- Sin nombres de archivo en el backend, persistencia, credenciales, servicios de terceros ni acceso al shell.
- Respuestas de error acotadas, JSON, `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.
- Cabeceras de seguridad en Vercel, incluida CSP, y API same-origin sin CORS abierto.
- `Permissions-Policy` bloquea cámara, micrófono y geolocalización: la demo no los necesita.

En una publicación real también deben configurarse controles de abuso y límites de frecuencia en el proveedor, observabilidad sin audio ni datos personales, y una política de privacidad/retención adecuada. No subir secretos al repositorio.

## Siguientes etapas

1. Validar BPM y acordes con grabaciones etiquetadas y distintas interpretaciones rítmicas.
2. Añadir decodificación segura de formatos adicionales y análisis de acordes/tonalidad.
3. Diseñar búsqueda de similitud sobre huellas musicales y un catálogo con derechos claros.
4. Añadir letras y enlaces de reproducción solo mediante proveedores autorizados y mostrar límites/atribución.
