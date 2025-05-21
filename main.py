import discord
from discord.ext import commands
from discord import app_commands
import requests
import random
import time
import re
import os
import asyncio
from io import BytesIO
import datetime

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global storage for user data
user_data = {}

def sleep():
    """Small sleep with random variance to simulate human behavior"""
    t = 0.01
    t += t * random.uniform(-0.1, 0.1)
    time.sleep(t)
    
def human_readable_size(size_bytes):
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
    i = 0
    while size_bytes >= 1024 and i < len(suffixes)-1:
        size_bytes /= 1024.0
        i += 1
    f = ('%.2f' % size_bytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

def format_timestamp(timestamp):
    """Format ISO timestamp to readable date"""
    try:
        dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except:
        return timestamp

async def fetch_audio_location(asset_id, place_id, roblox_cookie):
    """Fetch the audio URL location from Roblox API"""
    try:
        # Check if asset_id is numeric
        try:
            asset_id = int(asset_id)
        except ValueError:
            return None

        body_array = [{
            "assetId": asset_id,
            "assetType": "Audio",
            "requestId": "0"
        }]

        headers = {
            "User-Agent": "Roblox/WinInet",
            "Content-Type": "application/json",
            "Cookie": f".ROBLOSECURITY={roblox_cookie}",
            "Roblox-Place-Id": str(place_id),
            "Accept": "*/*",
            "Roblox-Browser-Asset-Request": "true"
        }
        
        response = await asyncio.to_thread(
            lambda: requests.post('https://assetdelivery.roblox.com/v2/assets/batch', 
                                headers=headers, json=body_array, timeout=30)
        )

        if response.status_code == 200:
            json_data = response.json()
            
            if not json_data or len(json_data) == 0:
                return None
                
            obj = json_data[0]
            if "locations" in obj and obj["locations"] and "location" in obj["locations"][0]:
                return obj["locations"][0]["location"]
            
        # Try alternative asset delivery endpoint if the first one fails
        alt_url = f"https://assetdelivery.roblox.com/v1/asset/?id={asset_id}"
        alt_response = await asyncio.to_thread(
            lambda: requests.get(alt_url, headers=headers, timeout=30)
        )
        
        if alt_response.status_code == 200:
            return alt_url
            
        return None
    except Exception as e:
        print(f"Error fetching audio location: {e}")
        return None

def sanitize_filename(name):
    """Clean up filename to be safe for saving"""
    sanitized_name = re.sub(r'[\\/*?"<>|:]', '', name)
    return sanitized_name.strip().replace(" ", "_")[:100]  # Limit length

async def fetch_asset_details(asset_id):
    """Get detailed asset information from Roblox API"""
    try:
        # Try multiple API endpoints
        apis = [
            f"https://economy.roproxy.com/v2/assets/{asset_id}/details",
            f"https://economy.roblox.com/v2/assets/{asset_id}/details",
            f"https://api.roblox.com/marketplace/productinfo?assetId={asset_id}"
        ]
        
        for api_url in apis:
            try:
                response = await asyncio.to_thread(
                    lambda: requests.get(api_url, timeout=15)
                )
                if response.status_code == 200:
                    asset_info = response.json()
                    return asset_info
            except Exception:
                continue
                
        return None
    except Exception as e:
        print(f"Error fetching asset details: {e}")
        return None

async def create_asset_embed(asset_info, asset_id):
    """Create a Discord embed with asset information"""
    embed = discord.Embed(
        title=f"🎵 {asset_info.get('Name', asset_info.get('name', 'Unknown Audio'))}",
        color=discord.Color.blue(),
        url=f"https://www.roblox.com/library/{asset_id}/"
    )
    
    if 'Description' in asset_info:
        embed.description = asset_info['Description'][:200] + "..." if len(asset_info['Description']) > 200 else asset_info['Description']
    
    if 'Created' in asset_info:
        embed.add_field(name="Created", value=format_timestamp(asset_info['Created']), inline=True)
    if 'Updated' in asset_info:
        embed.add_field(name="Updated", value=format_timestamp(asset_info['Updated']), inline=True)
    
    if 'Creator' in asset_info:
        creator = asset_info['Creator']
        if creator and 'Name' in creator:
            embed.add_field(
                name="Creator", 
                value=f"[{creator['Name']}](https://www.roblox.com/users/{creator.get('Id', '')}/profile)",
                inline=True
            )
    
    if 'PriceInRobux' in asset_info and asset_info['PriceInRobux'] is not None:
        embed.add_field(name="Price", value=f"🟢 {asset_info['PriceInRobux']} Robux", inline=True)
    elif 'IsLimited' in asset_info and asset_info['IsLimited']:
        embed.add_field(name="Status", value="🔴 Limited Item", inline=True)
    
    if 'AssetType' in asset_info:
        embed.set_footer(text=f"Asset Type: {asset_info['AssetType']} • ID: {asset_id}")
    else:
        embed.set_footer(text=f"ID: {asset_id}")
    
    return embed

async def download_audio_file(asset_id, place_id, roblox_cookie):
    """Download a single audio file and return the file path and asset info"""
    try:
        asset_info = await fetch_asset_details(asset_id)
        if not asset_info:
            return None, None, f"Could not fetch information for asset {asset_id}"
            
        asset_name = asset_info.get('Name', asset_info.get('name', f'UnknownAsset_{asset_id}'))
        sanitized_asset_name = sanitize_filename(asset_name)
        audio_url = await fetch_audio_location(asset_id, place_id, roblox_cookie)
        
        if not audio_url:
            return None, None, f"Could not fetch audio URL for asset {asset_id}"
        
        headers = {
            "User-Agent": "Roblox/WinInet",
            "Cookie": f".ROBLOSECURITY={roblox_cookie}"
        }
        
        response = await asyncio.to_thread(
            lambda: requests.get(audio_url, headers=headers, timeout=30)
        )
        
        if response.status_code != 200:
            return None, None, f"Failed to download asset {asset_id}: HTTP {response.status_code}"
            
        os.makedirs("audio_files", exist_ok=True)
        file_path = os.path.join("audio_files", f"{sanitized_asset_name}.ogg")
        
        with open(file_path, "wb") as f:
            f.write(response.content)
            
        return file_path, asset_info, None
    except Exception as e:
        return None, None, f"Error downloading asset {asset_id}: {str(e)}"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Set custom status
    activity = discord.Activity(
        name="Roblox Audio",
        type=discord.ActivityType.listening,
        details="Downloading audio files"
    )
    await bot.change_presence(activity=activity)
    print('------')

@bot.command(name="setcookie")
async def set_cookie(ctx, cookie=None):
    """Set your Roblox cookie (DM only for security)"""
    try:
        await ctx.message.delete()
    except:
        pass
        
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.author.send("🔒 **Security Notice**\nFor your account's safety, please only set your cookie in DMs with me!")
        return
        
    if not cookie:
        await ctx.send("❌ **Missing Cookie**\nPlease provide your `.ROBLOSECURITY` cookie like this:\n`!setcookie YOUR_COOKIE_HERE`")
        return
        
    user_id = str(ctx.author.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["cookie"] = cookie
    
    embed = discord.Embed(
        title="✅ Cookie Set Successfully",
        description="Your Roblox cookie has been securely stored.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="Important Security Note",
        value="• Never share your cookie with anyone\n• If you suspect it's compromised, regenerate it immediately\n• Use this bot only in DMs",
        inline=False
    )
    embed.set_footer(text="Your cookie is stored only in memory and will be lost when the bot restarts")
    
    await ctx.send(embed=embed)

@bot.command(name="setplaceid")
async def set_place_id(ctx, place_id=None):
    """Set the Roblox place ID for audio downloads"""
    if not place_id:
        embed = discord.Embed(
            title="❌ Missing Place ID",
            description="Please provide a valid Roblox place ID:\n`!setplaceid YOUR_PLACE_ID`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
        
    try:
        # Simple validation
        int(place_id)
    except ValueError:
        embed = discord.Embed(
            title="❌ Invalid Place ID",
            description="The place ID must be a numeric value.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
        
    user_id = str(ctx.author.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["place_id"] = place_id
    
    embed = discord.Embed(
        title="✅ Place ID Set",
        description=f"Successfully set Place ID to: `{place_id}`",
        color=discord.Color.green()
    )
    embed.add_field(
        name="Next Steps",
        value="You can now use `!download ASSET_ID` to get audio files from this place.",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="download")
async def download_audio(ctx, *asset_ids):
    """Download multiple audio files from Roblox"""
    user_id = str(ctx.author.id)
    
    if user_id not in user_data or "cookie" not in user_data[user_id]:
        embed = discord.Embed(
            title="❌ Cookie Not Set",
            description="You need to set your Roblox cookie first!\nUse `!setcookie` in DMs.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
        
    if user_id not in user_data or "place_id" not in user_data[user_id]:
        embed = discord.Embed(
            title="❌ Place ID Not Set",
            description="You need to set a Place ID first!\nUse `!setplaceid YOUR_PLACE_ID`.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    if not asset_ids:
        embed = discord.Embed(
            title="❌ Missing Asset IDs",
            description="Please provide at least one asset ID:\n`!download ASSET_ID1 ASSET_ID2 ...`",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    roblox_cookie = user_data[user_id]["cookie"]
    place_id = user_data[user_id]["place_id"]
    
    progress_msg = await ctx.send(f"⏳ **Starting Download**\nProcessing {len(asset_ids)} audio files...")
    
    successful = []
    failed = []
    
    for i, asset_id in enumerate(asset_ids, 1):
        try:
            await progress_msg.edit(content=f"🔍 **Downloading** ({i}/{len(asset_ids)})\nProcessing asset `{asset_id}`...")
            file_path, asset_info, error = await download_audio_file(asset_id, place_id, roblox_cookie)
            
            if error:
                failed.append(f"❌ `{asset_id}`: {error}")
                continue
                
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Create embed with asset info
            embed = await create_asset_embed(asset_info, asset_id)
            embed.add_field(
                name="File Info",
                value=f"Size: {human_readable_size(file_size)}\nFormat: OGG",
                inline=False
            )
            
            with open(file_path, "rb") as f:
                await ctx.send(
                    content=f"✅ Successfully downloaded audio!",
                    embed=embed,
                    file=discord.File(f, filename=f"{sanitize_filename(asset_info.get('Name', asset_info.get('name', f'audio_{asset_id}')))}.ogg")
                )
            
            successful.append(asset_id)
            await asyncio.sleep(1)  # Rate limit protection
            
        except Exception as e:
            failed.append(f"❌ `{asset_id}`: {str(e)}")
    
    # Create result embed
    result_embed = discord.Embed(
        title="📊 Download Results",
        color=discord.Color.blue()
    )
    result_embed.add_field(
        name="Summary",
        value=f"✅ **Success:** {len(successful)}\n❌ **Failed:** {len(failed)}",
        inline=False
    )
    
    if failed:
        failures_text = "\n".join(failed[:5])  # Show first 5 failures
        if len(failed) > 5:
            failures_text += f"\n...and {len(failed) - 5} more"
        result_embed.add_field(
            name="Failed Downloads",
            value=failures_text,
            inline=False
        )
    
    await progress_msg.edit(content=None, embed=result_embed)
    
    # Cleanup
    if os.path.exists("audio_files"):
        for file in os.listdir("audio_files"):
            try:
                os.remove(os.path.join("audio_files", file))
            except:
                pass

@bot.command(name="commands")
async def commands_help(ctx):
    """Show available commands"""
    embed = discord.Embed(
        title="🤖 Roblox Audio Downloader Help",
        description="All available commands for the bot",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🔐 Authentication",
        value="• `!setcookie [cookie]` - Set your Roblox cookie (DM only)\n• `!setplaceid [place_id]` - Set the Roblox place ID",
        inline=False
    )
    
    embed.add_field(
        name="🎵 Audio Commands",
        value="• `!download [asset_ids...]` - Download multiple audio files\nExample: `!download 12345 67890`",
        inline=False
    )
    
    embed.add_field(
        name="🛠️ Utility",
        value="• `!commands` - Show this help menu",
        inline=False
    )
    
    embed.set_footer(text="For security, always use cookie-related commands in DMs")
    
    await ctx.send(embed=embed)

# Slash Commands
@bot.tree.command(name="setcookie", description="Set your Roblox cookie (DM only for security)")
@app_commands.describe(cookie="Your Roblox .ROBLOSECURITY cookie")
async def slash_set_cookie(interaction: discord.Interaction, cookie: str):
    if not isinstance(interaction.channel, discord.DMChannel):
        embed = discord.Embed(
            title="🔒 Security Notice",
            description="For your account's safety, please only set your cookie in DMs with me!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
        
    user_id = str(interaction.user.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["cookie"] = cookie
    
    embed = discord.Embed(
        title="✅ Cookie Set Successfully",
        description="Your Roblox cookie has been securely stored.",
        color=discord.Color.green()
    )
    embed.add_field(
        name="Important Security Note",
        value="• Never share your cookie with anyone\n• If you suspect it's compromised, regenerate it immediately",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="setplaceid", description="Set the Roblox place ID for audio downloads")
@app_commands.describe(place_id="The numeric Roblox place ID")
async def slash_set_place_id(interaction: discord.Interaction, place_id: str):
    try:
        # Simple validation
        int(place_id)
    except ValueError:
        embed = discord.Embed(
            title="❌ Invalid Place ID",
            description="The place ID must be a numeric value.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
        
    user_id = str(interaction.user.id)
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]["place_id"] = place_id
    
    embed = discord.Embed(
        title="✅ Place ID Set",
        description=f"Successfully set Place ID to: `{place_id}`",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="download", description="Download an audio file from Roblox")
@app_commands.describe(asset_id="The Roblox audio asset ID")
async def slash_download_audio(interaction: discord.Interaction, asset_id: str):
    user_id = str(interaction.user.id)
    
    if user_id not in user_data or "cookie" not in user_data[user_id]:
        embed = discord.Embed(
            title="❌ Cookie Not Set",
            description="You need to set your Roblox cookie first!\nUse `/setcookie` in DMs.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
        
    if user_id not in user_data or "place_id" not in user_data[user_id]:
        embed = discord.Embed(
            title="❌ Place ID Not Set",
            description="You need to set a Place ID first!\nUse `/setplaceid YOUR_PLACE_ID`.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await interaction.response.defer()
    
    roblox_cookie = user_data[user_id]["cookie"]
    place_id = user_data[user_id]["place_id"]
    
    try:
        progress_msg = await interaction.followup.send(f"🔍 **Processing**\nDownloading asset `{asset_id}`...")
        file_path, asset_info, error = await download_audio_file(asset_id, place_id, roblox_cookie)
        
        if error:
            embed = discord.Embed(
                title=f"❌ Download Failed",
                description=f"Could not download asset `{asset_id}`",
                color=discord.Color.red()
            )
            embed.add_field(name="Error", value=error, inline=False)
            await progress_msg.edit(content=None, embed=embed)
            return
            
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create embed with asset info
        embed = await create_asset_embed(asset_info, asset_id)
        embed.add_field(
            name="File Info",
            value=f"Size: {human_readable_size(file_size)}\nFormat: OGG",
            inline=False
        )
        
        with open(file_path, "rb") as f:
            await interaction.followup.send(
                content=f"✅ **Download Complete**",
                embed=embed,
                file=discord.File(f, filename=f"{sanitize_filename(asset_info.get('Name', asset_info.get('name', 'audio_' + str(asset_id))))}.ogg")
            )
        
        await progress_msg.delete()
        
    except Exception as e:
        embed = discord.Embed(
            title=f"❌ Unexpected Error",
            description=f"An error occurred while processing asset `{asset_id}`",
            color=discord.Color.red()
        )
        embed.add_field(name="Details", value=str(e), inline=False)
        await interaction.followup.send(embed=embed)
    
    # Cleanup
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass

@bot.tree.command(name="commands", description="Show available commands")
async def slash_commands_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Roblox Audio Downloader Help",
        description="All available commands for the bot",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🔐 Authentication",
        value="• `/setcookie [cookie]` - Set your Roblox cookie (DM only)\n• `/setplaceid [place_id]` - Set the Roblox place ID",
        inline=False
    )
    
    embed.add_field(
        name="🎵 Audio Commands",
        value="• `/download [asset_id]` - Download an audio file",
        inline=False
    )
    
    embed.add_field(
        name="🛠️ Utility",
        value="• `/commands` - Show this help menu",
        inline=False
    )
    
    embed.set_footer(text="For security, always use cookie-related commands in DMs")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run the bot with your token
if __name__ == "__main__":
    # IMPORTANT: Replace this with your bot token or use environment variables
    bot.run("MTM3NDQzMDE0MTExNTI3MzI3Nw.GSHhaI.bLqjW-wtkN0QWnMuAOc4eNK5g27fQGYPBmTBLM")
