"""Agent implementations.

Each concrete agent lives in its own submodule and subclasses `Agent`. The
abstract base in `base.py` wraps every call in the lifecycle context manager
so individual agents only carry business logic.
"""

from agency.agents._generation_base import GenerationAgentBase
from agency.agents.background_removal_agent import BackgroundRemovalAgent
from agency.agents.base import Agent
from agency.agents.brief_clarification import BriefClarification
from agency.agents.business_design_generator import BusinessDesignGenerator
from agency.agents.delivery_packager import DeliveryPackager
from agency.agents.headshot_generator import HeadshotGenerator
from agency.agents.logo_generator import LogoGenerator
from agency.agents.prompt_engineering import PromptEngineering
from agency.agents.social_graphics_generator import SocialGraphicsGenerator
from agency.agents.technical_qc import TechnicalQC
from agency.agents.text_renderer import TextRenderer
from agency.agents.thumbnail_generator import ThumbnailGenerator
from agency.agents.visual_qc import VisualQC

__all__ = [
    "Agent",
    "BackgroundRemovalAgent",
    "BriefClarification",
    "BusinessDesignGenerator",
    "DeliveryPackager",
    "GenerationAgentBase",
    "HeadshotGenerator",
    "LogoGenerator",
    "PromptEngineering",
    "SocialGraphicsGenerator",
    "TechnicalQC",
    "TextRenderer",
    "ThumbnailGenerator",
    "VisualQC",
]
