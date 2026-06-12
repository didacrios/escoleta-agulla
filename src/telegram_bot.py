#!/usr/bin/env python3
"""
Bot de Telegram per enviar el menú diari escolar.
"""
import json
import os
import asyncio
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import click


def load_menu_data(json_file: str) -> dict:
    """Carrega les dades del menú des del JSON."""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_menu_for_date(menu_data: dict, target_date: date) -> dict | None:
    """
    Busca el menú per una data específica.

    Args:
        menu_data: Dades del menú carregades del JSON
        target_date: Data a buscar

    Returns:
        Diccionari amb el menú del dia o None si no es troba
    """
    target_date_str = target_date.isoformat()

    for day in menu_data.get('days', []):
        if day['date'] == target_date_str:
            return day

    return None


def format_menu_message(day_data: dict, month_name: str) -> str:
    """
    Formata el menú en un missatge bonic per Telegram.

    Args:
        day_data: Dades del dia amb el menú
        month_name: Nom del mes en català

    Returns:
        Text formatat per enviar (amb HTML)
    """
    message = f"🍽️ <b>Menú - {day_data['weekday']} {day_data['dia']} de {month_name}</b>\n\n"

    if day_data.get('notes'):
        message += f"📝 <i>{', '.join(day_data['notes'])}</i>\n\n"

    message += f"🥣 <b>Primer plat:</b> {day_data['primer']}\n\n"
    message += f"🍖 <b>Segon plat:</b> {day_data['segon']}\n\n"
    message += f"🍨 <b>Postre:</b> {day_data['postre']}\n\n"
    message += "Bon profit! 😋"

    return message


async def send_menu(bot_token: str, chat_id: str, message: str):
    """Envia un missatge per Telegram."""
    try:
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML'
        )
        return True
    except TelegramError as e:
        raise Exception(f"Error enviant missatge: {e}")


@click.command()
@click.option('--json-file', '-f', type=click.Path(exists=True),
              help='Fitxer JSON amb el menú')
@click.option('--date', '-d', 'date_str', type=str,
              help='Data en format YYYY-MM-DD (per defecte: avui)')
def main(json_file: str, date_str: str):
    """
    Envia el menú diari per Telegram.

    Exemples:
        # Enviar el menú d'avui
        python src/telegram_bot.py -f menu/data/novembre_2025.json

        # Enviar el menú d'una data específica
        python src/telegram_bot.py -f menu/data/novembre_2025.json -d 2025-11-15
    """
    # Carregar variables d'entorn
    load_dotenv()

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        click.echo("❌ Error: TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID han d'estar definits al .env")
        return

    # Determinar la data
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            click.echo(f"❌ Error: Format de data incorrecte. Usa YYYY-MM-DD")
            return
    else:
        target_date = date.today()

    click.echo(f"📅 Buscant menú per: {target_date.isoformat()}")

    # Detectar automàticament el fitxer JSON si no s'especifica
    if not json_file:
        # Buscar el fitxer corresponent al mes actual
        month_names = {
            1: 'gener', 2: 'febrer', 3: 'març', 4: 'abril',
            5: 'maig', 6: 'juny', 7: 'juliol', 8: 'agost',
            9: 'setembre', 10: 'octubre', 11: 'novembre', 12: 'desembre'
        }
        month_name = month_names[target_date.month]
        json_file = f"menu/data/{month_name}_{target_date.year}.json"

        if not Path(json_file).exists():
            click.echo(f"❌ Error: No s'ha trobat el fitxer {json_file}")
            click.echo("   Especifica el fitxer amb --json-file")
            return

    click.echo(f"📖 Llegint: {json_file}")

    # Carregar el menú
    try:
        menu_data = load_menu_data(json_file)
    except Exception as e:
        click.echo(f"❌ Error carregant el menú: {e}")
        return

    # Buscar el menú del dia
    day_menu = get_menu_for_date(menu_data, target_date)

    if not day_menu:
        click.echo(f"❌ No s'ha trobat menú per la data {target_date.isoformat()}")
        click.echo(f"   Aquest menú conté dates des de {menu_data['days'][0]['date']} "
                   f"fins {menu_data['days'][-1]['date']}")
        return

    # Formatar i enviar el missatge
    message = format_menu_message(day_menu, menu_data['month'])

    click.echo("\n📤 Enviant missatge...\n")
    click.echo("-" * 60)
    click.echo(message)
    click.echo("-" * 60)

    try:
        asyncio.run(send_menu(bot_token, chat_id, message))
        click.echo("\n✅ Missatge enviat correctament!")
    except Exception as e:
        click.echo(f"\n❌ Error: {e}")


if __name__ == '__main__':
    main()

