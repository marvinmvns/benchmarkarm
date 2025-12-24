"""
Controle do Botão do ReSpeaker HAT.
"""
import logging
import time
from typing import Callable

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO não disponível. Botão desabilitado.")

class ButtonController:
    """Controlador do botão do ReSpeaker."""
    
    BUTTON_PIN = 17  # GPIO 17 é o padrão do botão no ReSpeaker 2-Mic e 4-Mic
    
    def __init__(self, callback: Callable[[bool], None], initial_state: bool = False):
        """
        Args:
            callback: Função chamada quando estado muda via botão. 
                      Recebe bool (True=Ligado, False=Desligado).
            initial_state: Estado inicial
        """
        self.enabled = GPIO_AVAILABLE
        self.callback = callback
        self.is_active = initial_state
        self._last_press = 0
        
        if self.enabled:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                # Adicionar evento
                GPIO.add_event_detect(
                    self.BUTTON_PIN, 
                    GPIO.FALLING, 
                    callback=self._on_press, 
                    bouncetime=300
                )
                logger.info(f"🔘 Botão inicializado no GPIO {self.BUTTON_PIN}")
            except Exception as e:
                logger.error(f"Erro ao iniciar botão: {e}")
                self.enabled = False
    
    def _on_press(self, channel):
        """Callback interno do GPIO."""
        now = time.time()
        if now - self._last_press < 0.5: # Debounce extra
            return
        self._last_press = now
        
        self.is_active = not self.is_active
        state_str = "LIGADO" if self.is_active else "DESLIGADO"
        logger.info(f"🔘 Botão pressionado: {state_str}")
        
        if self.callback:
            try:
                self.callback(self.is_active)
            except Exception as e:
                logger.error(f"Erro no callback do botão: {e}")
            
    def cleanup(self):
        if self.enabled:
            try:
                GPIO.remove_event_detect(self.BUTTON_PIN)
                GPIO.cleanup(self.BUTTON_PIN)
            except Exception:
                pass
