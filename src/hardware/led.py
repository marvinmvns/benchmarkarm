"""
Controle de LEDs do ReSpeaker HAT.

Baseado no repositório https://github.com/respeaker/mic_hat
Suporta ReSpeaker 2-Mic HAT (3 LEDs APA102) e 4-Mic HAT.
"""

import logging
import threading
import time
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# Tentar importar spidev (só funciona no Raspberry Pi)
try:
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False
    logger.warning("spidev não disponível. LEDs desabilitados.")


class APA102:
    """
    Driver para LEDs APA102 (DotStar).
    Baseado em https://github.com/tinue/APA102_Pi
    """
    
    MAX_BRIGHTNESS = 31  # 0b11111
    LED_START = 0b11100000
    
    def __init__(
        self,
        num_led: int = 3,
        brightness: int = 8,
        order: str = 'rgb',
        bus: int = 0,
        device: int = 1,
    ):
        self.num_led = num_led
        self.brightness = min(brightness, self.MAX_BRIGHTNESS)
        
        # Mapear ordem RGB
        self.rgb_map = {'r': 0, 'g': 1, 'b': 2}
        self.order = [self.rgb_map.get(c, i) for i, c in enumerate(order.lower()[:3])]
        
        # Buffer de pixels
        self.leds = [[0, 0, 0] for _ in range(num_led)]
        
        # SPI
        self.spi = None
        if SPI_AVAILABLE:
            try:
                self.spi = spidev.SpiDev()
                self.spi.open(bus, device)
                self.spi.max_speed_hz = 8000000
            except Exception as e:
                logger.warning(f"Erro ao abrir SPI: {e}")
                self.spi = None
    
    def set_pixel(self, index: int, r: int, g: int, b: int):
        """Define cor de um pixel."""
        if 0 <= index < self.num_led:
            self.leds[index] = [r, g, b]
    
    def set_all(self, r: int, g: int, b: int):
        """Define todos os pixels com a mesma cor."""
        for i in range(self.num_led):
            self.leds[i] = [r, g, b]
    
    def show(self):
        """Envia dados para os LEDs."""
        if not self.spi:
            return
        
        try:
            # Start frame (32 bits de zeros)
            data = [0] * 4
            
            # LED frames
            for led in self.leds:
                data.append(self.LED_START | self.brightness)
                # Aplicar ordem RGB
                data.append(led[self.order[2]])  # Blue
                data.append(led[self.order[1]])  # Green
                data.append(led[self.order[0]])  # Red
            
            # End frame
            data += [0xFF] * ((self.num_led + 15) // 16)
            
            self.spi.xfer2(data)
        except Exception as e:
            logger.error(f"Erro ao enviar dados para LEDs: {e}")
    
    def off(self):
        """Desliga todos os LEDs."""
        self.set_all(0, 0, 0)
        self.show()
    
    def cleanup(self):
        """Libera recursos."""
        self.off()
        if self.spi:
            self.spi.close()


class LEDController:
    """
    Controlador de LEDs do ReSpeaker com padrões de iluminação.
    
    Estados:
    - idle: LEDs desligados ou brilho mínimo
    - listening: Piscando azul (capturando áudio)
    - processing: Girando amarelo/laranja (processando)
    - success: Verde por 1 segundo
    - error: Vermelho por 1 segundo
    """
    
    # Cores padrão (R, G, B)
    COLORS = {
        'off': (0, 0, 0),
        'blue': (0, 0, 255),
        'green': (0, 255, 0),
        'red': (255, 0, 0),
        'yellow': (255, 200, 0),
        'orange': (255, 100, 0),
        'white': (255, 255, 255),
        'purple': (200, 0, 255),
    }
    
    def __init__(
        self,
        num_leds: int = 3,
        brightness: int = 8,
        enabled: bool = True,
    ):
        self.enabled = enabled and SPI_AVAILABLE
        self.num_leds = num_leds
        self.brightness = brightness
        
        self._apa102: Optional[APA102] = None
        self._current_state = 'idle'
        self._running = False
        self._animation_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        if self.enabled:
            try:
                self._apa102 = APA102(num_led=num_leds, brightness=brightness)
                self._apa102.off()
                logger.info(f"🔵 LEDs inicializados ({num_leds} LEDs, brilho {brightness})")
            except Exception as e:
                logger.warning(f"Erro ao inicializar LEDs: {e}")
                self.enabled = False
    
    @property
    def is_available(self) -> bool:
        """Verifica se os LEDs estão disponíveis."""
        return self.enabled and self._apa102 is not None
    
    def _set_color(self, color: Tuple[int, int, int]):
        """Define todos os LEDs com uma cor."""
        if not self.is_available:
            return
        self._apa102.set_all(*color)
        self._apa102.show()
    
    def _animate_blink(self, color: Tuple[int, int, int], interval: float = 0.5):
        """Animação de piscar."""
        on = True
        while not self._stop_event.is_set():
            if on:
                self._set_color(color)
            else:
                self._set_color(self.COLORS['off'])
            on = not on
            self._stop_event.wait(interval)
    
    def _animate_rotate(self, colors: List[Tuple[int, int, int]], interval: float = 0.2):
        """Animação de rotação."""
        offset = 0
        while not self._stop_event.is_set():
            for i in range(self.num_leds):
                color = colors[(i + offset) % len(colors)]
                self._apa102.set_pixel(i, *color)
            self._apa102.show()
            offset = (offset + 1) % self.num_leds
            self._stop_event.wait(interval)
    
    def _start_animation(self, animation_func, *args):
        """Inicia uma animação em thread separada."""
        self._stop_animation()
        self._stop_event.clear()
        self._animation_thread = threading.Thread(
            target=animation_func,
            args=args,
            daemon=True
        )
        self._animation_thread.start()
    
    def _stop_animation(self):
        """Para a animação atual."""
        self._stop_event.set()
        if self._animation_thread and self._animation_thread.is_alive():
            self._animation_thread.join(timeout=1)
        self._animation_thread = None
    
    def idle(self):
        """Estado ocioso - LEDs desligados."""
        if not self.enabled:
            return
        self._current_state = 'idle'
        self._stop_animation()
        self._set_color(self.COLORS['off'])
    
    def listening(self):
        """Capturando áudio - LEDs piscando azul."""
        if not self.enabled:
            return
        self._current_state = 'listening'
        self._start_animation(self._animate_blink, self.COLORS['blue'], 0.3)
        logger.debug("🔵 LEDs: modo listening (azul piscando)")
    
    def processing(self):
        """Processando - LEDs girando amarelo/laranja."""
        if not self.enabled:
            return
        self._current_state = 'processing'
        colors = [self.COLORS['yellow'], self.COLORS['orange'], self.COLORS['off']]
        self._start_animation(self._animate_rotate, colors, 0.15)
        logger.debug("🟡 LEDs: modo processing (amarelo girando)")
    
    def success(self, duration: float = 1.0):
        """Sucesso - Verde por alguns segundos."""
        if not self.enabled:
            return
        self._current_state = 'success'
        self._stop_animation()
        self._set_color(self.COLORS['green'])
        logger.debug("🟢 LEDs: modo success (verde)")
        
        # Timer para voltar ao idle
        def reset():
            time.sleep(duration)
            if self._current_state == 'success':
                self.idle()
        
        threading.Thread(target=reset, daemon=True).start()
    
    def error(self, duration: float = 1.0):
        """Erro - Vermelho por alguns segundos."""
        if not self.enabled:
            return
        self._current_state = 'error'
        self._stop_animation()
        self._set_color(self.COLORS['red'])
        logger.debug("🔴 LEDs: modo error (vermelho)")
        
        # Timer para voltar ao idle
        def reset():
            time.sleep(duration)
            if self._current_state == 'error':
                self.idle()
        
        threading.Thread(target=reset, daemon=True).start()
    
    def wakeup(self):
        """Ativação - Efeito de wakeup."""
        if not self.enabled:
            return
        self._current_state = 'wakeup'
        self._stop_animation()
        
        # Efeito de fade in
        for brightness in range(0, 26, 5):
            factor = brightness / 25
            color = tuple(int(c * factor) for c in self.COLORS['purple'])
            self._set_color(color)
            time.sleep(0.05)
        
        logger.debug("🟣 LEDs: modo wakeup (roxo)")
    
    def off(self):
        """Desliga os LEDs."""
        self.idle()
    
    def cleanup(self):
        """Libera recursos."""
        self._stop_animation()
        if self._apa102:
            self._apa102.cleanup()
        logger.info("LEDs liberados")


# Instância global (lazy loading)
_led_controller: Optional[LEDController] = None


def get_led_controller(
    num_leds: int = 3,
    brightness: int = 8,
    enabled: bool = True,
) -> LEDController:
    """Retorna o controlador de LEDs (singleton)."""
    global _led_controller
    if _led_controller is None:
        _led_controller = LEDController(
            num_leds=num_leds,
            brightness=brightness,
            enabled=enabled,
        )
    return _led_controller
