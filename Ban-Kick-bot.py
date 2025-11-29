import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

# .env laden
load_dotenv()

# Debug: Pfad und Token checken
current_dir = os.getcwd()
print(f"Aktueller Ordner: {current_dir}")
print(f".env-Pfad existiert: {os.path.exists('.env')}")
token = os.getenv('DISCORD_TOKEN')
print(f"Gefundener Token (gekürzt): {token[:20] if token else 'NICHT GEFUNDEN'}...")

# Bot-Setup: Intents aktivieren
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Konfiguration
TICKET_CATEGORY = "Tickets"  # Passe an, falls "Basics"
ARCHIVE_CATEGORY = "Ticket Archiv"  # Archiv-Kategorie
SUPPORT_CHANNEL_ID = 1443933155475325089  # Deine Kanal-ID
ADMIN_ROLE_NAME = "HLL Admin"  # Rolle für Schließen (oder höher)
SUPPORT_ROLE_NAME = "Support"  # Optional: Füge hier den Namen der Support-Rolle ein, falls vorhanden

# Modal für Grund-Eingabe (neues UX-Feature)
class TicketModal(discord.ui.Modal, title="Ticket-Grund angeben"):
    reason = discord.ui.TextInput(
        label="Beschreibe dein Anliegen (optional)",
        placeholder="z.B. 'Ban' oder 'Kick' oder 'Feedback'",
        required=False,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        print(f"🔄 Modal-Submit von {interaction.user}: Grund = '{self.reason.value}'")
        try:
            await interaction.response.defer()  # Defer, um Timeout bei langer Operation zu vermeiden
            await create_ticket_channel(interaction, self.reason.value or "Kein Grund angegeben")
        except Exception as e:
            print(f"❌ Modal-Submit-Fehler: {e}")
            try:
                await interaction.followup.send(f"Fehler beim Erstellen des Tickets: {str(e)}", ephemeral=True)
            except:
                print("❌ Followup-Fehler – User sieht nichts")

# View-Klasse für den Button (persistent)
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket Erstellen", style=discord.ButtonStyle.primary, emoji="📝", custom_id="ticket_create")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"🔘 Button geklickt von {interaction.user}")
        await interaction.response.send_modal(TicketModal())  # Direkt senden – kein Defer davor!

# Neue View für Close-Button im Ticket (nur HLL Admin oder höher)
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # 5 Min. Timeout

    @discord.ui.button(label="Schließen", style=discord.ButtonStyle.success, emoji="🟢")
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check für HLL Admin oder höhere Rolle (basierend auf Position)
        admin_role = discord.utils.get(interaction.guild.roles, name=ADMIN_ROLE_NAME)
        if not admin_role:
            await interaction.response.send_message("❌ Nur HLL Admin dürfen Tickets schließen!", ephemeral=True)
            return
        if not any(role.position >= admin_role.position for role in interaction.user.roles):
            await interaction.response.send_message(f"❌ Nur HLL Admin dürfen Tickets schließen!", ephemeral=True)
            return

        channel = interaction.channel
        if channel.name.startswith("ticket-"):
            # User-ID des Ticket-Erstellers extrahieren
            try:
                user_id = int(channel.name.split('-')[1])
                ticket_user = interaction.guild.get_member(user_id)
                if ticket_user:
                    # Benutzer aus Overwrites entfernen (setzt auf Default-Rechte, sieht Kanal nicht mehr)
                    await channel.set_permissions(ticket_user, overwrite=None)
                    print(f"✅ Ticket-Ersteller {ticket_user} hat Zugang zu {channel.name} verloren.")
                else:
                    print(f"⚠️ Ticket-Ersteller mit ID {user_id} nicht im Server gefunden.")
            except (ValueError, IndexError):
                print(f"❌ Fehler beim Extrahieren der User-ID aus {channel.name}")

            # Archiv-Kategorie erstellen/finden
            archive_category = discord.utils.get(interaction.guild.categories, name=ARCHIVE_CATEGORY)
            if not archive_category:
                archive_category = await interaction.guild.create_category(ARCHIVE_CATEGORY)

            # Kanal in Archiv verschieben
            embed = discord.Embed(title="Ticket geschlossen",
                                  description="Dieses Ticket wurde archiviert. Danke für deine Rückmeldung!",
                                  color=discord.Color.green())
            await interaction.response.send_message(embed=embed)
            await channel.edit(category=archive_category)
            print(f"✅ Ticket-Kanal {channel.name} archiviert von {ADMIN_ROLE_NAME}+ {interaction.user}!")

# Hilfsfunktion: Ticket-Kanal erstellen (getrennt für Reuse)
async def create_ticket_channel(interaction: discord.Interaction, reason: str):
    print(f"🔨 Erstelle Ticket für {interaction.user} mit Grund: {reason}")
    user_id = interaction.user.id
    category = discord.utils.get(interaction.guild.categories, name=TICKET_CATEGORY)
    if not category:
        raise ValueError(f"Kategorie '{TICKET_CATEGORY}' nicht gefunden! Erstelle sie manuell.")

    existing_ticket = discord.utils.get(category.channels, name=f"ticket-{user_id}")
    if existing_ticket:
        await interaction.followup.send(f"Du hast schon ein Ticket: {existing_ticket.mention}", ephemeral=True)
        return

    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
    }

    # Bestimmte Rollen hinzufügen: HLL Admin (immer) und Support (falls konfiguriert)
    admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
    if admin_role:
        overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
        print(f"✅ Admin-Rolle '{ADMIN_ROLE_NAME}' für Ticket-Zugriff hinzugefügt.")

    support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        print(f"✅ Support-Rolle '{SUPPORT_ROLE_NAME}' für Ticket-Zugriff hinzugefügt.")
    else:
        print(f"ℹ️ Support-Rolle '{SUPPORT_ROLE_NAME}' nicht gefunden – überspringe.")

    channel = await guild.create_text_channel(
        name=f"ticket-{user_id}",
        category=category,
        overwrites=overwrites,
        topic=f"Ticket von {interaction.user.mention} | Grund: {reason}"
    )

    embed = discord.Embed(
        title="🆕 Ticket erstellt!",
        description=f"Hallo {interaction.user.mention},\n\nDein Ticket wurde erstellt. Beschreibe dein Anliegen hier. Ein Teammitglied wird sich **schnellstmöglich** melden!\n\n**Grund:** {reason}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Schließe das Ticket", value="Nur HLL Admin oder höher können schließen (Button unten).", inline=False)
    view = TicketCloseView()  # Close-Button hinzufügen
    message = await channel.send(embed=embed, view=view)

    await interaction.followup.send(f"Ticket erstellt: {channel.mention}", ephemeral=True)
    print(f"✅ Ticket-Kanal {channel.name} erstellt!")

@bot.event
async def on_ready():
    print(f'{bot.user} ist online!')
    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)} Commands synchronisiert.')
    except Exception as e:
        print(f'Sync-Fehler: {e}')

    # Persistent View hinzufügen (wichtig für alte Buttons!)
    try:
        bot.add_view(TicketView())
        print("✅ Persistent View hinzugefügt!")
    except Exception as e:
        print(f"❌ View-Hinzufügen-Fehler: {e}")

    # Embed senden (nur wenn nicht schon da)
    channel = bot.get_channel(SUPPORT_CHANNEL_ID)
    if not channel:
        print(f"❌ Fehler: Kanal-ID {SUPPORT_CHANNEL_ID} nicht gefunden. Überprüfe die ID!")
        return
    print(f"✅ Kanal gefunden: {channel.name} (ID: {channel.id})")

    # Check auf bestehende Embed (einfach: suche nach View-Nachricht)
    existing = None
    try:
        async for msg in channel.history(limit=10):
            if msg.embeds and msg.components:
                existing = msg
                break
    except Exception as e:
        print(f"❌ History-Check-Fehler: {e}")

    if not existing:
        embed = discord.Embed(
            title="Support & Contact🤝",
            description="Bitte schreibe dein Anliegen nach Erstellen des Tickets in den Ticket-Kanal.\nEin Admin wird sich bei dir melden! ❤️‍🩹\n\nPlease include your request in your ticket after creating it.\nA admin will be there to Help you! ❤️‍🩹",
            color=discord.Color.green()
        )
        view = TicketView()
        try:
            await channel.send(embed=embed, view=view)
            print(f"✅ Support-Embed mit Button in Kanal {channel.name} gesendet!")
        except Exception as e:
            print(f"❌ Send-Fehler: {e} (Check Bot-Rechte: Send Messages?)")
    else:
        print("Support-Embed existiert schon – überspringe.")

# Slash-Command (nutzt Hilfsfunktion)
@bot.tree.command(name="ticket", description="Erstelle ein Support-Ticket")
@app_commands.describe(reason="Grund für dein Ticket (optional)")
async def create_ticket(interaction: discord.Interaction, reason: str = "Kein Grund angegeben"):
    await interaction.response.defer(ephemeral=True)  # Defer für längere Verarbeitung
    await create_ticket_channel(interaction, reason)

# Bot starten
if not token:
    print("Fehler: DISCORD_TOKEN nicht gefunden! Check .env-Datei.")
    input("Drücke Enter, um zu beenden...")  # Pausiert, damit du's siehst
    exit(1)
bot.run(token)