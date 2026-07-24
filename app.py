import discord
from discord.ext import commands
import re
import json
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ARCHIVO_DATOS = "wordle_datos.json"

# Detecta si el mensaje es el resumen oficial (contiene la corona y las menciones)
REGEX_GANADORES_APP = re.compile(r"👑\s*[1-6X]/6:\s*(.+)", re.IGNORECASE)
# Detecta el número de Wordle en el texto O en el embed (ej. "Wordle No. 1859", "Wordle #1859" o "Wordle 1859")
REGEX_NUMERO_WORDLE = re.compile(r"(?:Wordle\s+No\.\s+|Wordle\s+#|Wordle\s+)([0-9,]{3,})", re.IGNORECASE)

def cargar_datos():
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "puntos": {},        # { "user_id": puntos_totales (float) }
        "dias_premiados": [] # Lista de números de Wordles ya procesados
    }

def guardar_datos(datos):
    with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4)

async def enviar_tabla_ranking(canal):
    """
    Función auxiliar para generar y enviar el Embed del ranking a un canal específico.
    Se ejecuta automáticamente al procesar un resumen o al usar el comando !ranking.
    """
    datos = cargar_datos()
    puntos = datos.get("puntos", {})

    if not puntos:
        await canal.send("Todavía no hay puntos acumulados en el ranking.")
        return

    ranking_ordenado = sorted(puntos.items(), key=lambda x: float(x[1]), reverse=True)

    embed = discord.Embed(title="📊 Ranking General de Wordle", color=discord.Color.green())
    
    texto_ranking = ""
    for posicion, (user_id, pts) in enumerate(ranking_ordenado, start=1):
        nombre = f"Usuario ID: {user_id}"
        
        if user_id.isdigit():
            try:
                usuario = await bot.fetch_user(int(user_id))
                nombre = usuario.display_name
            except:
                nombre = f"Usuario ID: {user_id}"
        elif user_id.startswith("usuario_"):
            nombre = user_id.replace("usuario_", "")
        
        pts_float = float(pts)
        pts_str = f"{int(pts_float)}" if pts_float.is_integer() else f"{pts_float:.2f}".rstrip("0").rstrip(".")
            
        texto_ranking += f"**{posicion}.** {nombre} — **{pts_str}** pts\n"

    embed.description = texto_ranking
    await canal.send(embed=embed)

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")

@bot.event
async def on_message(message):
    # Ignorar mensajes generados por este mismo bot
    if message.author == bot.user:
        return

    # 1. FILTRO DE AUTOR: Solo intentamos leer resúmenes si el remitente es la aplicación Wordle
    # (Verifica si el nombre del autor contiene "wordle", sea la app oficial o un webhook de prueba)
    if "wordle" in message.author.name.lower():
        match_corona = REGEX_GANADORES_APP.search(message.content)
        if match_corona:
            datos = cargar_datos()

            # 2. Buscar el número de Wordle en el texto del mensaje O en el recuadro negro (Embed)
            wordle_id = None
            match_num = REGEX_NUMERO_WORDLE.search(message.content)
            if match_num:
                wordle_id = match_num.group(1).replace(",", "")
                
            if not wordle_id and message.embeds:
                for embed in message.embeds:
                    texto_embed = f"{embed.title or ''} {embed.description or ''} {embed.author.name if embed.author else ''}"
                    match_embed = REGEX_NUMERO_WORDLE.search(texto_embed)
                    if match_embed:
                        wordle_id = match_embed.group(1).replace(",", "")
                        break
            
            if not wordle_id:
                wordle_id = f"msg_{message.id}"

            # 3. SISTEMA ANTITRAMPAS: Evitar duplicados
            if wordle_id in datos["dias_premiados"]:
                return

            # 4. Extraer ganadores (Versión mejorada: mixta de menciones y texto plano)
            ganadores = []
            texto_linea_corona = match_corona.group(1)
            # Separamos la línea por espacios y limpiamos posibles comas o puntos
            tokens = [t.strip().rstrip(",.") for t in texto_linea_corona.split()]

            for token in tokens:
                if not token:
                    continue
                
                encontrado = False
                # A) Intentamos ver si esta palabra corresponde a alguien mencionado en Discord
                for usuario in message.mentions:
                    if (f"<@{usuario.id}>" in token or 
                        f"<@!{usuario.id}>" in token or 
                        token.lstrip("@").lower() == usuario.name.lower() or 
                        (usuario.display_name and token.lstrip("@").lower() == usuario.display_name.lower())):
                        
                        if str(usuario.id) not in ganadores:
                            ganadores.append(str(usuario.id))
                        encontrado = True
                        break
                
                # B) Si no era una mención real (texto plano), lo guardamos como usuario de texto
                if not encontrado:
                    nombre_limpio = token.lstrip("@")
                    if nombre_limpio:
                        id_texto = f"usuario_{nombre_limpio}"
                        if id_texto not in ganadores:
                            ganadores.append(id_texto)

            if ganadores:
                # 5. Calcular y guardar puntos
                puntos_a_sumar = 1.0 / len(ganadores)

                for uid in ganadores:
                    puntaje_actual = float(datos["puntos"].get(uid, 0))
                    datos["puntos"][uid] = round(puntaje_actual + puntos_a_sumar, 2)

                datos["dias_premiados"].append(wordle_id)
                guardar_datos(datos)

                # 6. REACCIÓN Y DISPARO AUTOMÁTICO DEL RANKING
                await message.add_reaction("🏆")
                await enviar_tabla_ranking(message.channel)

    # Permitir que el bot siga procesando comandos normalmente (para que funcione escribir !ranking)
    await bot.process_commands(message)

@bot.command(name="ranking")
async def ranking(ctx):
    """
    Muestra la tabla de posiciones acumulada al escribir el comando manualmente.
    """
    await enviar_tabla_ranking(ctx.channel)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    bot.run(token)