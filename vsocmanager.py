import datetime
from discord.ext import commands, tasks
import discord
import sqlitecloud
import asyncio
import random
import os
from discord.ui.button import Button, ButtonStyle
from discord.ui import View

# Configuration variables
ADMIN_ROLE_NAME = "VSOC-CORE TEAM🌟"
MODERATOR_ROLE_NAME = "VSOC-MODERATORS👮"
PROJECT_ADMINS_ROLE_ID = 1249376903589003294
BOT_TOKEN = "Your_Bot_token"
ALLOWED_ROLES = [1235216146781831220, 1234884140461985804, 1234884716096655392]
LEADERBOARD_CHANNEL_ID = 1235225849335124028
LEADERBOARD_DISPLAY_ID = 1235225970315624519
LOG_CHANNEL_ID = 1239144159324016662
PAGE_SIZE = 25
PARTICIPANTS_PAGE_SIZE = 5

bot = commands.Bot(command_prefix='&', intents=discord.Intents.all())

# Cloud SQLite connection
CLOUD_DB_URL = 'Your_SQLiteCloud_ConnectionString'

def get_cloud_cursor():
    conn = sqlitecloud.connect(CLOUD_DB_URL)
    cursor = conn.cursor()
    cursor.execute("USE DATABASE VSoC24Leaderboard")
    return conn, cursor

# Create the participants table if it does not exist
conn, cursor = get_cloud_cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS participants (
    rank VARCHAR DEFAULT 'UNRANKED',
    name TEXT CHECK (TRIM(name) <> ''),
    phone_number VARCHAR CHECK (
        (TRIM(phone_number) GLOB '+[0-9]*' AND LENGTH(REPLACE(TRIM(phone_number), '+', '')) BETWEEN 7 AND 10) OR 
        (TRIM(phone_number) GLOB '[0-9]*' AND LENGTH(TRIM(phone_number)) BETWEEN 7 AND 10)
    ),
    email TEXT PRIMARY KEY NOT NULL CHECK (TRIM(email) <> '' AND (email LIKE '%.com' OR email LIKE '%.in' OR email LIKE '%.me')),
    gitlink TEXT NOT NULL CHECK (TRIM(gitlink) <> '' AND gitlink LIKE '%github.com%'),
    score INTEGER DEFAULT 0
);
''')
conn.commit()
conn.close()

# Function to query the database and create the leaderboard embed
def update_leaderboard(page: int = 0):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("""
            SELECT name, COALESCE(score, 0), rank
            FROM participants
            ORDER BY score DESC
        """)
        all_participants = cursor.fetchall()
        conn.close()

        total_entries = len(all_participants)
        total_pages = (total_entries + PAGE_SIZE - 1) // PAGE_SIZE  # Calculate total number of pages

        start_index = page * PAGE_SIZE
        end_index = min((page + 1) * PAGE_SIZE, total_entries)
        participants = all_participants[start_index:end_index]

        leaderboard = discord.Embed(title="Leaderboard", color=discord.Color.gold())
        if participants:
            for participant in participants:
                rank_display = participant[2] if participant[2] else "Unranked"
                leaderboard.add_field(name=f"Rank {rank_display}", value=f"{participant[0]} - Score: {participant[1]}", inline=False)
        else:
            leaderboard.description = "No participants found in the database."

        leaderboard.set_footer(text=f"Page {page + 1}/{total_pages}")  # Display current page number in the footer

        return leaderboard
    except Exception as e:
        print(f"Error fetching leaderboard data: {e}")
        return None

# Function to update leaderboard message in specified channel with pagination
async def update_leaderboard_messages(page: int = 0):
    try:
        leaderboard_channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        leaderboard_display_channel = bot.get_channel(LEADERBOARD_DISPLAY_ID)
        
        leaderboard = update_leaderboard(page)  # Pass the page parameter to retrieve specific page of leaderboard
        if leaderboard:
            buttons = [
                Button(label="Previous", style=ButtonStyle.primary, custom_id="prev_page"),
                Button(label="Next", style=ButtonStyle.primary, custom_id="next_page")
            ]
            view = View()
            for button in buttons:
                view.add_item(button)

            if leaderboard_channel:
                async for message in leaderboard_channel.history():
                    if message.author == bot.user:
                        await message.edit(embed=leaderboard, view=view)
                        break
                else:
                    await leaderboard_channel.send(embed=leaderboard, view=view)
            
            if leaderboard_display_channel:
                async for message in leaderboard_display_channel.history():
                    if message.author == bot.user:
                        await message.edit(embed=leaderboard, view=view)
                        break
                else:
                    await leaderboard_display_channel.send(embed=leaderboard, view=view)
        else:
            print("Failed to update leaderboard. No data found.")
    except Exception as e:
        print(f"Error updating leaderboard messages: {e}")
        
# Scheduled task to update leaderboard
@tasks.loop(minutes=1)
async def update_leaderboard_task():
    try:
        await update_leaderboard_messages()
    except Exception as e:
        print(f"Error updating leaderboard: {e}")

# Command to manually update the leaderboard
@bot.command()
async def updateleaderboard(ctx):
    await update_leaderboard_messages(page=0)
    await log_operation(ctx, 'Manually updated the leaderboard.')
    leaderboard = update_leaderboard()
    if leaderboard:
        await ctx.send(embed=leaderboard)
        await log_operation(ctx, 'Manually updated the leaderboard.')
    else:
        await ctx.send("Failed to update leaderboard. Please try again later.")

# Function to add score to a participant in the database
@bot.command()
async def add_score(ctx, identifier: str, score: int):
    # Check if the user has the "Project Admins" role or any other allowed roles
    allowed_roles = [PROJECT_ADMINS_ROLE_ID] + ALLOWED_ROLES
    if any(role.id in allowed_roles for role in ctx.author.roles):
        await add_score_to_database(ctx, identifier, score)
    else:
        await ctx.send("You do not have permission to use this command.")
#FunctionADD
async def add_score_to_database(ctx, identifier, score):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("SELECT COALESCE(score, 0) FROM participants WHERE name = ? OR phone_number = ? OR email = ?", (identifier, identifier, identifier))
        current_score = cursor.fetchone()
        if current_score is not None:
            before_score = int(current_score[0])
            new_score = before_score + score
            cursor.execute("UPDATE participants SET score = ? WHERE name = ? OR phone_number = ? OR email = ?", (new_score, identifier, identifier, identifier))
            conn.commit()
            await update_ranks()  # Call update_ranks() after committing the score change
            conn.close()
            await log_operation(ctx, f"Score added for participant {identifier}.", before_score=before_score, after_score=new_score, change=score)
            embed = discord.Embed(title="Score Added", color=discord.Color.green())
            embed.add_field(name="Participant", value=identifier, inline=False)
            embed.add_field(name="Score", value=score, inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f'Participant {identifier} not found.')
            await log_operation(ctx, f"Attempted to add score for non-existent participant {identifier}.")
    except Exception as e:
        await ctx.send(f"Error updating score: {e}")
        await log_operation(ctx, f"Error updating score: {e}")

# Command to subtract score from a participant in the database
@bot.command()
async def subtract_score(ctx, identifier: str, score: int):
    # Check if the user has the "Project Admins" role
    allowed_roles = ALLOWED_ROLES
    if any(role.id in allowed_roles for role in ctx.author.roles):
        await subtract_score_from_database(ctx, identifier, score)
    else:
        await ctx.send("You do not have permission to use this command.")
#functionSUB
async def subtract_score_from_database(ctx, identifier, score):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("SELECT COALESCE(score, 0) FROM participants WHERE name = ? OR phone_number = ? OR email = ?", (identifier, identifier, identifier))
        current_score = cursor.fetchone()
        if current_score is not None:
            before_score = int(current_score[0])
            new_score = before_score - score  # Subtract score from current score
            cursor.execute("UPDATE participants SET score = ? WHERE name = ? OR phone_number = ? OR email = ?", (new_score, identifier, identifier, identifier))
            conn.commit()
            await update_ranks()  # Call update_ranks() after committing the score change
            conn.close()
            await log_operation(ctx, f"Score subtracted for participant {identifier}.", before_score=before_score, after_score=new_score, change=-score)
            embed = discord.Embed(title="Score Subtracted", color=discord.Color.red())
            embed.add_field(name="Participant", value=identifier, inline=False)
            embed.add_field(name="Score", value=score, inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f'Participant {identifier} not found.')
            await log_operation(ctx, f"Attempted to subtract score for non-existent participant {identifier}.")
    except Exception as e:
        await ctx.send(f"Error updating score: {e}")
        await log_operation(ctx, f"Error updating score: {e}")

# Function to add participant to the database
async def add_participant(name, phone, email, gitlink, score=0):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("SELECT COUNT(*) FROM participants")
        participant_count = cursor.fetchone()[0]
        rank = "UNRANKED" if score == 0 else f"P{participant_count + 1}"  # Set rank based on score
        
        cursor.execute("INSERT INTO participants (rank, name, phone_number, email, gitlink, score) VALUES (?, ?, ?, ?, ?, ?)", (rank, name, phone, email, gitlink, score))
        conn.commit()
        await update_ranks()  # Call update_ranks() after adding the participant
        conn.close()

        await update_ranks()
        print(f"Participant {name} added to the database.")
    except Exception as e:
        print(f"Error adding participant: {e}")
        raise

# Command to add participant
@bot.command()
async def addparticipant(ctx, name: str, phone: str, email: str, gitlink: str):
    allowed_roles = ALLOWED_ROLES  # Ensure this list is correct and does not include 'Project Admin' role
    if any(role.id in allowed_roles for role in ctx.author.roles):
        try:
            await add_participant(name, phone, email, gitlink)
            await ctx.send(f'Participant {name} added to the database.')
            await log_operation(ctx, f'Participant {name} added to the database.')
        except Exception as e:
            await ctx.send(f'Failed to add participant: {e}')
            await log_operation(ctx, f'Failed to add participant: {e}')
    else:
        await ctx.send("You do not have permission to use this command.")

# Command to remove participant
@bot.command()
async def removeparticipant(ctx, identifier: str):
    # Check if the user has one of the allowed roles
    allowed_roles = ALLOWED_ROLES
    if any(role.id in allowed_roles for role in ctx.author.roles):
        try:
            # Check if the provided identifier is a valid email
            if '@' not in identifier or '.' not in identifier:
                await ctx.send("Please provide a valid email address to remove the participant.")
                return            
            await remove_participant(identifier)
            await ctx.send(f'Participant with email {identifier} removed from the database.')
            await log_operation(ctx, f'Participant with email {identifier} removed from the database.')
        except Exception as e:
            await ctx.send(f'Failed to remove participant: {e}')
            await log_operation(ctx, f'Failed to remove participant: {e}')
    else:
        await ctx.send("You do not have permission to use this command.")

# Function to remove participant from the database
async def remove_participant(email):
    conn, cursor = get_cloud_cursor()
    cursor.execute("DELETE FROM participants WHERE email = ?", (email,))
    conn.commit()
    await update_ranks()  # Call update_ranks() after removing the participant
    conn.close()

# Command to display participants with pagination===========================
@bot.command()
async def participants(ctx):
    allowed_roles = ALLOWED_ROLES 
    if any(role.id in allowed_roles for role in ctx.author.roles):
        await display_participants(ctx, page=0)  # Display the first page
    else:
        await ctx.send("You do not have permission to use this command.")

# Function to display participants for a specific page
async def display_participants(ctx, page: int):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("""
            SELECT name, phone_number, email, gitlink, score
            FROM participants
            LIMIT ? OFFSET ?
        """, (PARTICIPANTS_PAGE_SIZE, page * PARTICIPANTS_PAGE_SIZE))
        participants = cursor.fetchall()
        conn.close()

        if participants:
            embed = format_participants_embed(participants, page)
            message = await ctx.send(embed=embed)

            # Add pagination buttons if needed
            total_entries = get_total_participants_count()  # Assuming this function exists
            total_pages = (total_entries + PARTICIPANTS_PAGE_SIZE - 1) // PARTICIPANTS_PAGE_SIZE
            if total_pages > 1:
                components = [
                    [
                        Button(label="Previous", custom_id="prev_page", style=ButtonStyle.gray),
                        Button(label="Next", custom_id="next_page", style=ButtonStyle.gray)
                    ]
                ]
                await message.edit(embed=embed, components=components)

    except Exception as e:
        await ctx.send(f"Error fetching participants: {e}")

# Event listener for pagination buttons
@bot.event
async def on_button_click(interaction):
    if interaction.component.custom_id in ["prev_page", "next_page"]:
        page = int(interaction.message.embeds[0].footer.text.split('/')[0].strip().split(' ')[-1]) - 1
        if interaction.component.custom_id == "prev_page":
            page -= 1
        elif interaction.component.custom_id == "next_page":
            page += 1
        await interaction.respond(embed=await display_participants_embed(interaction, page))

# Function to retrieve participants for a specific page
async def display_participants_embed(interaction, page: int):
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("""
            SELECT name, phone_number, email, gitlink, score
            FROM participants
            LIMIT ? OFFSET ?
        """, (PARTICIPANTS_PAGE_SIZE, page * PARTICIPANTS_PAGE_SIZE))
        participants = cursor.fetchall()
        conn.close()

        if participants:
            embed = format_participants_embed(participants, page)
            embed.set_footer(text=f"Page {page + 1}")
            return embed

    except Exception as e:
        await interaction.message.edit(content=f"Error fetching participants: {e}")

# Function to get the total count of participants
def get_total_participants_count():
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("SELECT COUNT(*) FROM participants")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Error fetching participants count: {e}")
        return 0
    
def format_participants_embed(participants, page: int):
    embed = discord.Embed(title="Participants", color=discord.Color.blue())
    start_index = page * PARTICIPANTS_PAGE_SIZE + 1
    for i, participant in enumerate(participants):
        embed.add_field(
            name=f"{start_index + i}. {participant[0]}",
            value=f"Phone: {participant[1]}\nEmail: {participant[2]}\nGitHub: {participant[3]}\nScore: {participant[4]}",
            inline=False
        )
    return embed

# Define a list of colors
COLORS = [discord.Color.blue(), discord.Color.green(), discord.Color.red(), discord.Color.orange(), discord.Color.purple()]

# Command to display all available commands with descriptions and examples
@bot.command()
async def commands(ctx):
    # Check if the user has the "Project Admins" role or any other allowed roles
    allowed_roles = ALLOWED_ROLES
    if any(role.id in allowed_roles for role in ctx.author.roles):
    # Define a list of tuples containing command, description, and example
        command_list = [
        ("&updateleaderboard", "Manually update the leaderboard.", "&updateleaderboard"),
        ("&add_score <name_or_phone> <score>", "Add score to a participant.", "&add_score \"John Doe\" 10"),
        ("&subtract_score <name_or_phone> <score>", "Subtract score from a participant.", "&subtract_score \"John Doe\" 5"),
        ("&addparticipant <name> <phone> <email> <gitlink>", "Add a new participant.", "&addparticipant \"John Doe\" +123456789 john@example.com github.com/johndoe"),
        ("&removeparticipant <name_or_phone>", "Remove a participant.", "&removeparticipant \"John Doe\""),
        ("&participants", "Display all participants.", "&participants"),
        ("&commands", "Display all available commands.", "&commands")
    ]

    # Choose a random color for the embed
    color = random.choice(COLORS)

    # Create an embed to display the commands
    embed = discord.Embed(title="Available Commands", color=color)
    for command, description, example in command_list:
        embed.add_field(name=command, value=f"Description: {description}\nExample: `{example}`", inline=False)
    
    # Add a note about using double quotes
    embed.set_footer(text='Note: Use double quotes if the name has spaces, e.g., &add_score \"John Doe\" 10.')

    await ctx.send(embed=embed)

# Function to update ranks based on scores
async def update_ranks():
    try:
        conn, cursor = get_cloud_cursor()
        # Retrieve participants ordered by score
        cursor.execute("SELECT name, COALESCE(score, 0) FROM participants ORDER BY score DESC")
        participants = cursor.fetchall()
        
        # Assign ranks to participants
        rank_counter = 0
        for idx, participant in enumerate(participants, start=1):
            if participant[1] == 0:
                rank = "UNRANKED"  # Assign "UNRANKED" rank for participants with score 0
            else:
                rank_counter += 1
                rank = f"P{rank_counter}"  # Assign ranks for participants with non-zero score
            cursor.execute("UPDATE participants SET rank = ? WHERE name = ?", (rank, participant[0]))

        conn.commit()
        conn.close()
        print("Ranks updated successfully.")
    except Exception as e:
        print(f"Error updating ranks: {e}")

# Function to log operations
async def log_operation(ctx, message, **kwargs):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title="Operation Log", description=message, color=discord.Color.purple())
        embed.add_field(name="User", value=ctx.author.mention, inline=False)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=False)
        embed.add_field(name="Timestamp", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        for key, value in kwargs.items():
            embed.add_field(name=key.replace('_', ' ').title(), value=value, inline=False)
        await log_channel.send(embed=embed)
    else:
        print(f"Log channel with ID {LOG_CHANNEL_ID} not found.")

# Event to log errors
@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f'An error occurred: {error}')
    await log_operation(ctx, f'Error occurred: {error}')

# Event to ensure the bot is ready
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user.name} ({bot.user.id})')
    update_leaderboard_task.start()
    
# Function to retrieve all participants from the database
def get_all_participants():
    try:
        conn, cursor = get_cloud_cursor()
        cursor.execute("SELECT COUNT(*) FROM participants")
        total_entries = cursor.fetchone()[0]
        conn.close()
        return int(total_entries)  # Ensure that the total_entries is returned as an integer
    except Exception as e:
        print(f"Error fetching all participants: {e}")
        return 0
    
# Button interaction handler
@bot.event
async def on_button_click(interaction):
    if interaction.custom_id in ["prev_page", "next_page"]:
        custom_id = interaction.custom_id
        message = interaction.message

        embed = message.embeds[0]
        current_page = 0
        
        # Extract numeric part from the footer text
        footer_text = embed.footer.text
        if footer_text:
            page_info = footer_text.split('/')[0].strip().split(' ')[-1]
            if page_info.isdigit():
                current_page = int(page_info) - 1  # Adjust to zero-based index

        total_entries = get_total_participants_count()  # Get total count of participants
        total_pages = (total_entries + PARTICIPANTS_PAGE_SIZE - 1) // PARTICIPANTS_PAGE_SIZE  # Calculate total number of pages

        new_page = current_page  # Default to current page

        if custom_id == 'prev_page':
            new_page = current_page - 1  # Go to previous page
            if new_page < 0:
                new_page = total_pages - 1  # Loop to last page if currently on the first page
        elif custom_id == 'next_page':
            new_page = current_page + 1  # Go to next page
            if new_page >= total_pages:
                new_page = 0  # Loop to first page if currently on the last page

        leaderboard = update_leaderboard(new_page)  # Retrieve updated leaderboard for the new page
        
        await interaction.response.defer(ephemeral=True)  # Acknowledge the interaction as ephemeral

        if leaderboard:
            leaderboard.set_footer(text=f"Page {new_page + 1}/{total_pages}")  # Update footer with new page number
            await interaction.followup.send(embed=leaderboard)

# Start the bot
bot.run(BOT_TOKEN)
