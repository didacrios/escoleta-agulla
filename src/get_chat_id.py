#!/usr/bin/env python3
"""
Script temporal per obtenir el Chat ID de Telegram.
Un cop obtingut, pots eliminar aquest fitxer.
"""
import click
from telegram import Bot
from telegram.error import TelegramError
import asyncio


async def get_updates(token: str):
    """Obtenir les últimes actualitzacions del bot."""
    try:
        bot = Bot(token=token)
        updates = await bot.get_updates()

        if not updates:
            click.echo("❌ No s'han trobat missatges.")
            click.echo("\n💡 Assegura't d'haver enviat un missatge al bot primer!")
            click.echo("   1. Cerca el teu bot a Telegram")
            click.echo("   2. Envia-li un missatge (ex: /start o 'hola')")
            click.echo("   3. Torna a executar aquest script\n")
            return

        click.echo("\n✅ Chat IDs trobats:\n")

        seen_chats = set()
        for update in updates:
            if update.message:
                chat_id = update.message.chat_id
                username = update.message.chat.username or "sense username"
                first_name = update.message.chat.first_name or ""

                if chat_id not in seen_chats:
                    click.echo(f"  📱 Chat ID: {chat_id}")
                    click.echo(f"     Nom: {first_name}")
                    click.echo(f"     Username: @{username}")
                    click.echo()
                    seen_chats.add(chat_id)

        click.echo("💾 Guarda el teu Chat ID al fitxer .env\n")

    except TelegramError as e:
        click.echo(f"❌ Error: {e}")
        click.echo("\n💡 Comprova que el token sigui correcte.")


@click.command()
@click.option('--token', '-t', prompt='Token del bot',
              help='Token del bot de Telegram')
def main(token: str):
    """
    Obtenir el Chat ID del teu bot de Telegram.

    Exemple:
        python src/get_chat_id.py --token "123456:ABC..."
    """
    click.echo("🔍 Buscant missatges del bot...\n")
    asyncio.run(get_updates(token))


if __name__ == '__main__':
    main()

