# Guía de la demostración con 20 personas

Objetivo: que unas 20 personas entren a la vez desde un link (en la compu o en
el celular, también si lo abren desde WhatsApp) y usen todo el sistema contra
esta PC: biblioteca, subir y descargar archivos, grupos, Mi espacio y el
asistente de IA. Todo gratis.

## 1. El día antes (una sola vez)

1. **Clave de Groq** en `.env` (`GROQ_API_KEY`). `iniciar.bat` la pide si falta.
2. **Recomendado: clave de Gemini** (`GEMINI_API_KEY`, gratis en
   https://aistudio.google.com/apikey). Da cupo extra al asistente, vectores para
   la búsqueda y revisión de imágenes. Sin ella todo funciona igual, con menos margen.
3. **Cuenta de administrador**: pon tu correo en `ADMIN_EMAILS` y créala antes
   de la demo (o `python manage.py admin tu.correo@ufg.edu.sv`).
4. **cloudflared** instalado: `winget install Cloudflare.cloudflared` (ya está en
   esta PC).
5. Prueba de carga sin gastar cuota (deja el puerto 5001 libre antes):

   ```bash
   python scripts/prueba_carga.py --aislado
   ```

   Debe terminar con 0 errores. Ver resultados en `docs/FASE_2.md`.
6. Que haya material: `python seed_test_data.py` con el servidor encendido crea
   documentos, grupos y cuentas de prueba (correos `@prueba.ufg.edu.sv`,
   contraseña en el propio script).

## 2. Encender

Doble clic en **`iniciar.bat`**. Al cabo de unos segundos la ventana muestra:

```
  UFG Knowledge Hub está encendido
  En esta PC:        http://127.0.0.1:5001
  Misma red Wi-Fi:   http://192.168.x.x:5001
  LINK PARA COMPARTIR (celular o compu, desde cualquier lugar):
      https://palabras-al-azar.trycloudflare.com
```

El link público ya queda copiado: pégalo en el grupo de WhatsApp. Funciona
mientras esa ventana esté abierta; la próxima vez será otro. Para apagar todo:
Ctrl+C o cerrar la ventana.

- Sin internet o sin cloudflared: `iniciar.bat` sigue mostrando la dirección de
  la red local (todos en el mismo Wi-Fi; Windows pide permitir Python en el
  firewall la primera vez).
- La PC no debe suspenderse durante la demo (Configuración → Energía).

## 3. Cómo entran los compañeros

**En el celular**

1. Abren el link. Si lo tocan dentro de WhatsApp se abre en su navegador
   interno: funciona igual (descargas incluidas), pero es más cómodo
   «Abrir en Chrome/Safari».
2. «Crea tu cuenta» con su correo **@ufg.edu.sv**. Otros correos no se aceptan.
3. Se mueven con la barra de abajo: Inicio, Asistente, Biblioteca, Grupos y
   Mi espacio. Notificaciones y menú, arriba.
4. Opcional: instalar la app. Android/Chrome: menú ⋮ → «Instalar app» (o el
   botón «Instalar app» del menú). iPhone/Safari: Compartir → «Agregar a
   pantalla de inicio». Queda con el ícono de la UFG y abre a pantalla completa.

**En la compu**: abren el link en cualquier navegador; el menú queda a la izquierda.

## 4. Guion sugerido (15 minutos)

1. **Registro**: todos crean su cuenta. Muestra que un Gmail se rechaza.
2. **Asistente**: «¿Qué material hay sobre bases de datos?». Se ven las luces
   mientras piensa, las citas [1] y las fuentes. Si muchos preguntan a la vez,
   verán «En cola: unos N s»: es la cuota gratuita repartiéndose.
3. **Biblioteca**: buscar, abrir un documento, vista previa (en el celular el PDF
   se abre en el visor del teléfono) y descargar.
4. **Subir**: cada uno sube un apunte. Aparece «En revisión» y a los pocos
   segundos la notificación «Archivo publicado»: no hizo falta que nadie lo aprobara.
5. **Vigilante**: el admin sube un `.exe` renombrado a `.pdf` → se rechaza al
   momento con el motivo. Un documento con «ignora tus instrucciones» escondido
   queda **en cuarentena** y aparece en **Seguridad** para aprobar o rechazar.
6. **Grupos**: crear uno, agregar compañeros, escribir en el chat y en el tablero.
7. **Seguridad** (admin): cuarentena, cuota de la IA que queda en cada modelo y
   espacio de los archivos.

## 5. Qué esperar con 20 personas

- Navegar, buscar, subir y descargar: respuestas por debajo de 40 ms en la PC
  (p95), sin errores.
- Asistente: unas 5 a 8 respuestas nuevas por minuto con la cuenta gratuita de
  Groq. Si las 20 personas preguntan a la vez, algunas esperan en cola; las
  preguntas repetidas salen al instante de la caché. Si se agotara la cuota, el
  asistente devuelve los documentos encontrados en lugar de un error.
- Vigilante: revisa en segundo plano; con 20 personas subiendo a la vez, los
  últimos archivos se publican unos minutos después.
- La PC sólo sirve la web (la IA está en la nube): el servidor usa poca memoria
  y CPU.

## 6. Si algo falla

| Síntoma | Qué hacer |
|---|---|
| El link no abre | Esperar 10-20 s (el nombre tarda en existir). Si sigue, cerrar y volver a abrir `iniciar.bat`. |
| «El puerto 5001 ya está en uso» | Quedó otro servidor abierto: cerrar esa ventana. |
| El asistente dice que la IA está al máximo | Es la cuota gratuita: esperar el tiempo indicado. Con clave de Gemini hay más margen. |
| Un archivo se queda «En revisión» mucho rato | El vigilante está esperando cupo de la IA; se reintenta solo. El admin puede verlo en Seguridad → En proceso. |
| Alguien quedó bloqueado al entrar | Son 15 minutos tras 5 intentos fallidos; esperar o usar otra cuenta. |
| Registro del servidor | `instance\servidor.log` y `instance\servidor-errores.log` |
