"""Envío de mensajes por la API oficial de WhatsApp (Meta Cloud API).

Configuración: Config.wa_phone_id y Config.wa_api_token (de developers.facebook.com).
En modo de prueba, Meta da un número de prueba y deja enviar a hasta 5 números
que agregues y verifiques — todo gratis.
"""

import json
import urllib.error
import urllib.request


class WhatsAppError(RuntimeError):
    pass


def enviar_texto(phone_id: str, token: str, destino: str, texto: str) -> dict:
    """Envía un mensaje de texto. `destino` con indicativo, sin +. Lanza WhatsAppError si falla."""
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    cuerpo = json.dumps({
        "messaging_product": "whatsapp",
        "to": destino,
        "type": "text",
        "text": {"body": texto[:4000]},
    }).encode()
    req = urllib.request.Request(
        url, data=cuerpo, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="replace")
        try:
            msg = json.loads(detalle)["error"]["message"]
        except Exception:
            msg = detalle[:200]
        raise WhatsAppError(msg) from e
    except urllib.error.URLError as e:
        raise WhatsAppError(f"No se pudo conectar: {e.reason}") from e
