#!/usr/bin/env python3
"""
Script per obtenir el Channel ID d'un canal de Telegram.
"""
import click
from telegram import Bot
from telegram.error import TelegramError
import asyncio


async def get_channel_info(token: str, channel_username: str):
    """Obtenir informació del canal."""
    try:
        bot = Bot(token=token)

        # Si no comença amb @, afegir-lo
        if not channel_username.startswith('@'):
            channel_username = f'@{channel_username}'

        # Obtenir informació del canal
        chat = await bot.get_chat(channel_username)

        click.echo("\n✅ Canal trobat!\n")
        click.echo(f"  📢 Nom: {chat.title}")
        click.echo(f"  🆔 Channel ID: {chat.id}")
        click.echo(f"  📝 Username: @{chat.username}")
        click.echo(f"  📋 Descripció: {chat.description or 'Sense descripció'}")
        click.echo()
        click.echo("💾 Guarda aquest Channel ID al fitxer .env com a TELEGRAM_CHAT_ID")
        click.echo("   (També actualitza'l als GitHub Secrets!)\n")

    except TelegramError as e:
        click.echo(f"❌ Error: {e}")
        click.echo("\n💡 Assegura't que:")
        click.echo("   1. El bot és administrador del canal")
        click.echo("   2. El username del canal és correcte (amb o sense @)")
        click.echo("   3. El token del bot és vàlid\n")


@click.command()
@click.option('--token', '-t', prompt='Token del bot',
              help='Token del bot de Telegram')
@click.option('--channel', '-c', prompt='Username del canal (ex: @menu_escoleta)',
              help='Username del canal (amb o sense @)')
def main(token: str, channel: str):
    """
    Obtenir el Channel ID d'un canal de Telegram.

    Exemple:
        python src/get_channel_id.py --token "123456:ABC..." --channel "@menu_escoleta"
    """
    click.echo("🔍 Buscant informació del canal...\n")
    asyncio.run(get_channel_info(token, channel))


if __name__ == '__main__':
    main()

