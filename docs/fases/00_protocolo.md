# Protocolo de fases (el agente lo lee al empezar cada sesión)

El analista abre una sesión nueva y escribe solo: «sigue».

1. Lee `CLAUDE.md › Estado` y abre `docs/fases/<fase en curso o siguiente>.md`. No leas otras fases ni specs que esa fase no cite.
2. Trabaja hasta cumplir su «Aceptación». Una fase puede ocupar varias sesiones: no la des por terminada con tests en rojo.
3. Si se agota el contexto: commit de lo que esté en verde, punto exacto de retorno en `Estado` (≤ 3 líneas) y para.
4. Al cumplir la aceptación, en este orden:
   a. `python -m tesis regresiones` → pega su tabla tal cual, sin resumirla.
   b. Regenera el informe de control (QCOM, 23/09/2026) y di qué apartados cambian (≤ 5 líneas).
   c. `git add -A && git commit -m "Fn: <resumen>"`.
   d. Marca la fase ☑ en `Estado` y para. No empieces la siguiente.
5. Prohibido dar algo por hecho sin la salida del comando que lo demuestra.

## Reglas de todas las fases
- Una fase = una parte del informe terminada de verdad: sus datos, sus entradas (04; hasta F6, en `tests/fixtures/<TICKER>/entradas.json`), sus plantillas de frases (06 §1), sus comprobaciones en la puerta de calidad (06 §3) y sus regresiones (07).
- Todo lo que se imprime o se ve en la interfaz, en español (02 › Lenguaje).
- Las partes aún no rehechas se imprimen con el código antiguo a través del adaptador del esqueleto (F1); cada fase retira el suyo.
- Entradas de prueba de QCOM y NFLX en `tests/fixtures/<TICKER>/entradas.json`, marcadas como de prueba.
- Los borrados propuestos en F0 (`narrativa.py`, SDK `anthropic`, `narrativas/`, restos) solo se ejecutan cuando el analista escriba en `Estado` «confirmo borrar».
