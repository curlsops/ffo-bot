#!/usr/bin/env python3
import bot
import config
import database
from bot.auth.permissions import PermissionChecker
from bot.cache.memory import InMemoryCache
from bot.client import FFOBot
from bot.commands.admin import AdminCommands
from bot.commands.faq import FAQCommands
from bot.commands.giveaway import GiveawayCommands, GiveawayView
from bot.commands.permissions import PermissionCommands
from bot.commands.polls import PollCommands
from bot.commands.privacy import PrivacyCommands
from bot.commands.quotebook import QuotebookCommands
from bot.commands.reactbot import ReactBotCommands
from bot.commands.reaction_roles import ReactionRoleCommands
from bot.commands.whitelist import WhitelistCommands
from bot.handlers.messages import MessageHandler
from bot.handlers.reactions import ReactionHandler
from bot.processors.media_downloader import MediaDownloader
from bot.processors.phrase_matcher import PhraseMatcher
from bot.processors.unit_converter import detect_and_convert
from bot.processors.voice_transcriber import VoiceTranscriber
from bot.services.minecraft_rcon import MinecraftRCONClient, parse_whitelist_list_response
from bot.services.mojang import username_exists
from bot.tasks.giveaway_manager import GiveawayManager
from bot.tasks.status_rotator import StatusRotator
from bot.utils.db import TRANSIENT_DB_ERRORS
from bot.utils.health import HealthCheckServer
from bot.utils.metrics import BotMetrics
from bot.utils.notifier import AdminNotifier
from bot.utils.rate_limiter import RateLimiter
from bot.utils.regex_validator import RegexValidator
from bot.utils.validation import InputValidator
from bot.utils.whitelist_cache import add_to_cache, get_cached_usernames, remove_from_cache, sync_from_rcon
from bot.utils.whitelist_channel import get_whitelist_channel_id, set_whitelist_channel
from config.settings import Settings
from database.connection import DatabasePool

if __name__ == "__main__":
    print("All modules imported successfully")
