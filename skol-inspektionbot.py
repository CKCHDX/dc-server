import discord
import os
from discord import app_commands
from discord.ext import commands
import datetime

intents = discord.Intents.default()
intents.members = True  # Required for nickname changes and member events
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Modal for Name + Class ---
class VerifyModal(discord.ui.Modal, title="School Verification"):
    name_class = discord.ui.TextInput(
        label="Enter your full name and class",
        placeholder="John Smith - 9B",
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Update nickname
        await interaction.user.edit(nick=self.name_class.value)

        # Remove Unverified role
        unverified_role = discord.utils.get(interaction.guild.roles, name="Unverified")
        if unverified_role:
            await interaction.user.remove_roles(unverified_role)

        # Assign Elever role
        elever_role = discord.utils.get(interaction.guild.roles, name="Elever")
        if elever_role:
            await interaction.user.add_roles(elever_role)

        await interaction.response.send_message(
            f"Welcome {self.name_class.value}! You are now verified and assigned the Elever role.",
            ephemeral=True
        )

# --- Button to open modal ---
class VerifyButton(discord.ui.View):
    @discord.ui.button(label="Verify", style=discord.ButtonStyle.green)
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

# --- Slash command /start ---
@bot.tree.command(name="start", description="Initialize the verification system")
@app_commands.checks.has_permissions(administrator=True)
async def start(interaction: discord.Interaction):
    view = VerifyButton()
    await interaction.response.send_message(
        "Click the button below to verify yourself:", view=view
    )

# --- Slash command /unverifyall ---
@bot.tree.command(name="unverifyall", description="Reset verification for all students")
@app_commands.checks.has_permissions(administrator=True)
async def unverifyall(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    unverified_role = discord.utils.get(interaction.guild.roles, name="Unverified")
    overifierade_role = discord.utils.get(interaction.guild.roles, name="overifierade elever")

    count = 0
    for member in interaction.guild.members:
        if member.guild_permissions.administrator or member.top_role.name in ["Owner", "Co-Owner"]:
            continue

        # Remove roles one by one safely
        roles_to_remove = [role for role in member.roles if role != interaction.guild.default_role]
        for role in roles_to_remove:
            try:
                await member.remove_roles(role)
            except discord.Forbidden:
                continue

        # Add unverified roles safely
        if unverified_role:
            try:
                await member.add_roles(unverified_role)
            except discord.Forbidden:
                pass
        if overifierade_role:
            try:
                await member.add_roles(overifierade_role)
            except discord.Forbidden:
                pass

        count += 1

    await interaction.followup.send(f"Unverified and reset {count} members.", ephemeral=True)
# --- Event: assign overifierade elever role on join ---
@bot.event
async def on_member_join(member: discord.Member):
    overifierade_role = discord.utils.get(member.guild.roles, name="overifierade elever")
    if overifierade_role:
        await member.add_roles(overifierade_role)

# --- Sync slash commands ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

# -------------------------------
# SECTION: Violation / Filter Library
# -------------------------------

FORBIDDEN_WORDS = [
    # Swedish racial/ethnic slurs
    "rasist", "svartskalle", "jude", "neger", "blatte", "invandrare",
    
    # English racial/ethnic slurs
    "nigger", "n1gger", "kike", "fag", "bitch", "chink", "spic",
    
    # Sexual / NSFW
    "sex", "porn", "nsfw", "slut", "whore", "fuck", "cum", "xxx",
    
    # Self-promotion / spam
    "discord.gg", "join my server", "https://", "http://", "t.me/",
    
    # Other harassment / insults
    "idiot", "stupid", "moron", "retard"
]


SPAM_COOLDOWN = 5  # seconds
MAX_STRIKES_24H = 3

user_strikes = {}  # {user_id: [(timestamp, reason), ...]}
user_last_message = {}  # {user_id: (last_content, timestamp)}

# -------------------------------
# SECTION: Violation / Message Handler
# -------------------------------

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.datetime.utcnow()
    user_id = message.author.id
    violation_channel = discord.utils.get(message.guild.text_channels, name="violation")

    violated = False  # Initialize first

    # Anti-spam
    last = user_last_message.get(user_id)
    if last:
        last_content, last_time = last
        delta = (now - last_time).total_seconds()
        if delta < SPAM_COOLDOWN and message.content == last_content:
            violated = True
    user_last_message[user_id] = (message.content, now)

    # Forbidden words
    content_lower = message.content.lower()
    if any(word in content_lower for word in FORBIDDEN_WORDS):
        violated = True

    if violated:
        # Delete message
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        # Update strikes
        strikes = user_strikes.get(user_id, [])
        strikes = [s for s in strikes if (now - s[0]).total_seconds() < 86400]
        strikes.append((now, "Violation"))
        user_strikes[user_id] = strikes
        strike_count = len(strikes)

        member = message.author
        reason = f"Violation (strike {strike_count})"

        # Escalation
        if strike_count == 2:
            try:
                await member.timeout(datetime.timedelta(seconds=60), reason=reason)
            except discord.Forbidden:
                pass
        elif strike_count == 3:
            try:
                await member.timeout(datetime.timedelta(seconds=600), reason=reason)
            except discord.Forbidden:
                pass
        elif strike_count >= MAX_STRIKES_24H:
            violation_role = discord.utils.get(message.guild.roles, name="Violation Zone")
            if violation_role:
                try:
                    await member.add_roles(violation_role, reason=reason)
                except discord.Forbidden:
                    pass

        # Log
        if violation_channel:
            await violation_channel.send(
                f"⚠️ {member.mention} violated rules in {message.channel.mention}\n"
                f"Message: {message.content}\n"
                f"Strike count: {strike_count}\n"
                f"Action: {'Timeout/Violation Zone' if strike_count >= 2 else 'Deleted'}"
            )
        return

    await bot.process_commands(message)



bot.run(os.getenv("DISCORD_TOKEN"))
