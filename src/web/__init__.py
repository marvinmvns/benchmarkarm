"""
Interface Web para configuração do Voice Processor.
Feature toggle - pode ser habilitada/desabilitada via configuração.
"""

from .server import WebServer, create_app

__all__ = ["WebServer", "create_app"]
