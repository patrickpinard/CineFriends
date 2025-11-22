"""Configuration du logging structuré pour l'application Dashboard

Ce module fournit des fonctions pour logger avec contexte structuré,
facilitant le debugging et le monitoring.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from flask import current_app, has_request_context, request
from flask_login import current_user


class StructuredLogger:
    """Logger avec contexte structuré"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def _get_context(self, **extra: Any) -> Dict[str, Any]:
        """Construit le contexte structuré pour le log"""
        context: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            **extra
        }
        
        # Ajouter le contexte de la requête si disponible
        if has_request_context():
            context["request"] = {
                "method": request.method,
                "path": request.path,
                "endpoint": request.endpoint,
                "remote_addr": request.remote_addr,
            }
            
            # Ajouter l'utilisateur si authentifié
            if current_user.is_authenticated:
                context["user"] = {
                    "id": current_user.id,
                    "username": current_user.username,
                    "role": current_user.role,
                }
        
        return context
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug avec contexte"""
        context = self._get_context(**kwargs)
        self.logger.debug(f"{message} | Context: {json.dumps(context, default=str)}")
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info avec contexte"""
        context = self._get_context(**kwargs)
        self.logger.info(f"{message} | Context: {json.dumps(context, default=str)}")
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning avec contexte"""
        context = self._get_context(**kwargs)
        self.logger.warning(f"{message} | Context: {json.dumps(context, default=str)}")
    
    def error(self, message: str, **kwargs: Any) -> None:
        """Log error avec contexte"""
        context = self._get_context(**kwargs)
        self.logger.error(f"{message} | Context: {json.dumps(context, default=str)}")
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception avec contexte et traceback"""
        context = self._get_context(**kwargs)
        self.logger.exception(f"{message} | Context: {json.dumps(context, default=str)}")


def get_logger(name: Optional[str] = None) -> StructuredLogger:
    """Récupère un logger structuré
    
    Args:
        name: Nom du logger (par défaut: nom du module appelant)
    
    Returns:
        Instance de StructuredLogger
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "app")
    
    logger = logging.getLogger(name)
    return StructuredLogger(logger)


def get_app_logger() -> StructuredLogger:
    """Récupère le logger de l'application Flask actuelle
    
    Returns:
        Instance de StructuredLogger utilisant current_app.logger
    """
    if has_request_context():
        return StructuredLogger(current_app.logger)
    else:
        # Fallback si pas de contexte de requête
        return StructuredLogger(logging.getLogger("app"))

