"""
Gerenciamento de energia para Raspberry Pi.
Implementa estratégias de economia de energia configuráveis.
"""

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class PowerMode(Enum):
    """Modos de energia."""
    PERFORMANCE = "performance"      # Máxima performance
    BALANCED = "balanced"            # Equilíbrio
    POWER_SAVE = "power_save"        # Economia de energia
    ULTRA_POWER_SAVE = "ultra_power_save"  # Economia máxima


@dataclass
class PowerProfile:
    """Perfil de energia."""
    mode: PowerMode
    cpu_governor: str
    cpu_freq_max: Optional[int]  # MHz, None = não limitar
    gpu_freq: Optional[int]      # MHz
    disable_hdmi: bool
    disable_wifi_power_save: bool
    disable_bluetooth: bool
    led_brightness: int          # 0-255
    audio_idle_timeout: int      # Segundos para desligar áudio idle
    process_nice: int            # Nice level para processos


# Perfis predefinidos
POWER_PROFILES = {
    PowerMode.PERFORMANCE: PowerProfile(
        mode=PowerMode.PERFORMANCE,
        cpu_governor="performance",
        cpu_freq_max=None,
        gpu_freq=500,
        disable_hdmi=False,
        disable_wifi_power_save=True,
        disable_bluetooth=False,
        led_brightness=255,
        audio_idle_timeout=0,
        process_nice=0,
    ),
    PowerMode.BALANCED: PowerProfile(
        mode=PowerMode.BALANCED,
        cpu_governor="ondemand",
        cpu_freq_max=None,
        gpu_freq=400,
        disable_hdmi=False,
        disable_wifi_power_save=False,
        disable_bluetooth=False,
        led_brightness=128,
        audio_idle_timeout=30,
        process_nice=5,
    ),
    PowerMode.POWER_SAVE: PowerProfile(
        mode=PowerMode.POWER_SAVE,
        cpu_governor="powersave",
        cpu_freq_max=600,
        gpu_freq=300,
        disable_hdmi=True,
        disable_wifi_power_save=False,
        disable_bluetooth=True,
        led_brightness=32,
        audio_idle_timeout=10,
        process_nice=10,
    ),
    PowerMode.ULTRA_POWER_SAVE: PowerProfile(
        mode=PowerMode.ULTRA_POWER_SAVE,
        cpu_governor="powersave",
        cpu_freq_max=400,
        gpu_freq=250,
        disable_hdmi=True,
        disable_wifi_power_save=False,
        disable_bluetooth=True,
        led_brightness=0,
        audio_idle_timeout=5,
        process_nice=15,
    ),
}


class PowerManager:
    """
    Gerenciador de energia para Raspberry Pi.

    Características:
    - Perfis de energia predefinidos
    - Ajuste dinâmico baseado em atividade
    - Controle de CPU, GPU, HDMI, WiFi, Bluetooth
    - LEDs do ReSpeaker
    - Modo idle automático
    """

    # Caminhos do sistema
    CPU_GOVERNOR_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
    CPU_FREQ_MAX_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
    CPU_FREQ_MIN_PATH = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq"
    GPU_FREQ_PATH = "/sys/class/devfreq/gpu/max_freq"

    def __init__(
        self,
        enabled: bool = True,
        default_mode: PowerMode = PowerMode.BALANCED,
        idle_timeout: float = 60.0,
        idle_mode: PowerMode = PowerMode.POWER_SAVE,
        auto_adjust: bool = True,
    ):
        """
        Inicializa o gerenciador de energia.

        Args:
            enabled: Se o gerenciamento está habilitado
            default_mode: Modo padrão
            idle_timeout: Tempo de inatividade para entrar em modo idle
            idle_mode: Modo para quando idle
            auto_adjust: Ajustar automaticamente baseado em atividade
        """
        self.enabled = enabled
        self.default_mode = default_mode
        self.idle_timeout = idle_timeout
        self.idle_mode = idle_mode
        self.auto_adjust = auto_adjust

        self._current_mode = default_mode
        self._is_idle = False
        self._last_activity = time.time()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._on_mode_change: Optional[Callable] = None

        # Verificar se é Raspberry Pi
        self._is_raspberry_pi = self._check_raspberry_pi()

        if self.enabled and not self._is_raspberry_pi:
            logger.warning("Não é Raspberry Pi. Gerenciamento de energia limitado.")

    def _check_raspberry_pi(self) -> bool:
        """Verifica se está rodando em Raspberry Pi."""
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read()
                return "Raspberry" in model
        except FileNotFoundError:
            return False

    def _run_command(self, cmd: list, check: bool = False) -> bool:
        """Executa comando do sistema."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check and result.returncode != 0:
                logger.warning(f"Comando falhou: {' '.join(cmd)}: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Erro ao executar comando: {e}")
            return False

    def _write_sys(self, path: str, value: str) -> bool:
        """Escreve em arquivo do sistema."""
        try:
            with open(path, "w") as f:
                f.write(value)
            return True
        except (PermissionError, FileNotFoundError) as e:
            logger.debug(f"Não foi possível escrever em {path}: {e}")
            return False

    def _read_sys(self, path: str) -> Optional[str]:
        """Lê arquivo do sistema."""
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except (PermissionError, FileNotFoundError):
            return None

    def set_mode(self, mode: PowerMode) -> bool:
        """
        Define modo de energia.

        Args:
            mode: Modo desejado

        Returns:
            True se aplicado com sucesso
        """
        if not self.enabled:
            return False

        profile = POWER_PROFILES.get(mode)
        if not profile:
            logger.error(f"Modo desconhecido: {mode}")
            return False

        success = True
        old_mode = self._current_mode

        # CPU Governor
        if self._is_raspberry_pi:
            for cpu in range(4):  # Pi Zero 2W tem 4 cores
                path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_governor"
                if not self._write_sys(path, profile.cpu_governor):
                    success = False

            # CPU Frequency Max
            if profile.cpu_freq_max:
                freq_khz = str(profile.cpu_freq_max * 1000)
                for cpu in range(4):
                    path = f"/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_max_freq"
                    self._write_sys(path, freq_khz)

        # HDMI
        if profile.disable_hdmi:
            self._run_command(["vcgencmd", "display_power", "0"])
        else:
            self._run_command(["vcgencmd", "display_power", "1"])

        # Bluetooth
        if profile.disable_bluetooth:
            self._run_command(["sudo", "rfkill", "block", "bluetooth"])
        else:
            self._run_command(["sudo", "rfkill", "unblock", "bluetooth"])

        # WiFi Power Save
        if profile.disable_wifi_power_save:
            self._run_command(["sudo", "iw", "wlan0", "set", "power_save", "off"])
        else:
            self._run_command(["sudo", "iw", "wlan0", "set", "power_save", "on"])

        # LEDs do ReSpeaker
        self._set_led_brightness(profile.led_brightness)

        # Ajustar nice dos processos atuais
        try:
            os.nice(profile.process_nice - os.nice(0))
        except (OSError, PermissionError):
            pass

        self._current_mode = mode

        if old_mode != mode:
            logger.info(f"Modo de energia alterado: {old_mode.value} -> {mode.value}")
            if self._on_mode_change:
                self._on_mode_change(old_mode, mode)

        return success

    def _set_led_brightness(self, brightness: int) -> None:
        """Define brilho dos LEDs do ReSpeaker."""
        # Tentar via GPIO (ReSpeaker 2-Mic)
        try:
            # LED path para ReSpeaker
            led_paths = [
                "/sys/class/leds/led0/brightness",
                "/sys/class/leds/led1/brightness",
            ]
            for path in led_paths:
                self._write_sys(path, str(brightness))
        except Exception:
            pass

    def activity_pulse(self) -> None:
        """Registra atividade (reseta timer de idle)."""
        self._last_activity = time.time()

        # Se estava em idle, voltar ao modo normal
        if self._is_idle and self.auto_adjust:
            self._is_idle = False
            self.set_mode(self.default_mode)

    def _idle_monitor(self) -> None:
        """Thread de monitoramento de idle."""
        while not self._stop_event.is_set():
            if self.auto_adjust:
                idle_time = time.time() - self._last_activity

                if idle_time >= self.idle_timeout and not self._is_idle:
                    self._is_idle = True
                    logger.info(f"Entrando em modo idle após {idle_time:.0f}s")
                    self.set_mode(self.idle_mode)

            self._stop_event.wait(10)  # Verificar a cada 10s

    def start(self) -> None:
        """Inicia monitoramento de energia."""
        if not self.enabled:
            return

        self._stop_event.clear()
        self.set_mode(self.default_mode)

        if self.auto_adjust:
            self._monitor_thread = threading.Thread(
                target=self._idle_monitor,
                daemon=True,
            )
            self._monitor_thread.start()

        logger.info(f"Gerenciador de energia iniciado (modo: {self.default_mode.value})")

    def stop(self) -> None:
        """Para monitoramento e restaura configurações."""
        self._stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

        # Restaurar modo padrão
        self.set_mode(PowerMode.BALANCED)
        logger.info("Gerenciador de energia parado")

    def get_status(self) -> dict:
        """Retorna status atual de energia."""
        status = {
            "enabled": self.enabled,
            "current_mode": self._current_mode.value,
            "is_idle": self._is_idle,
            "idle_time": time.time() - self._last_activity,
            "is_raspberry_pi": self._is_raspberry_pi,
        }

        # Informações do sistema
        if self._is_raspberry_pi:
            # Temperatura
            try:
                temp = subprocess.run(
                    ["vcgencmd", "measure_temp"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                status["temperature"] = temp
            except Exception:
                pass

            # Frequência da CPU
            try:
                freq = subprocess.run(
                    ["vcgencmd", "measure_clock", "arm"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                status["cpu_freq"] = freq
            except Exception:
                pass

            # Tensão
            try:
                volt = subprocess.run(
                    ["vcgencmd", "measure_volts"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                status["voltage"] = volt
            except Exception:
                pass

            # Throttling
            try:
                throttled = subprocess.run(
                    ["vcgencmd", "get_throttled"],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                status["throttled"] = throttled
            except Exception:
                pass

        return status

    def get_estimated_power(self) -> dict:
        """
        Retorna estimativa de consumo de energia.

        Returns:
            Dicionário com estimativas de consumo
        """
        # Estimativas baseadas em medições típicas (mW)
        base_consumption = {
            PowerMode.PERFORMANCE: 1800,
            PowerMode.BALANCED: 1200,
            PowerMode.POWER_SAVE: 800,
            PowerMode.ULTRA_POWER_SAVE: 500,
        }

        mode = self._current_mode
        base = base_consumption.get(mode, 1200)

        # Ajustes
        adjustments = 0
        profile = POWER_PROFILES.get(mode)

        if profile:
            if not profile.disable_hdmi:
                adjustments += 50
            if not profile.disable_bluetooth:
                adjustments += 30
            if profile.led_brightness > 0:
                adjustments += int(profile.led_brightness / 255 * 20)

        return {
            "mode": mode.value,
            "estimated_mw": base + adjustments,
            "estimated_ma_5v": (base + adjustments) / 5,
        }

    def on_mode_change(self, callback: Callable[[PowerMode, PowerMode], None]) -> None:
        """Registra callback para mudança de modo."""
        self._on_mode_change = callback

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


class AdaptivePowerManager(PowerManager):
    """
    Gerenciador de energia adaptativo.
    Ajusta automaticamente baseado em carga de trabalho e temperatura.
    """

    def __init__(
        self,
        temp_threshold_high: float = 70.0,
        temp_threshold_critical: float = 80.0,
        **kwargs,
    ):
        """
        Inicializa gerenciador adaptativo.

        Args:
            temp_threshold_high: Temperatura para reduzir performance
            temp_threshold_critical: Temperatura crítica
        """
        super().__init__(**kwargs)
        self.temp_threshold_high = temp_threshold_high
        self.temp_threshold_critical = temp_threshold_critical
        self._thermal_throttled = False

    def _get_temperature(self) -> Optional[float]:
        """Retorna temperatura da CPU em Celsius."""
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True,
                text=True,
            )
            # Output: temp=45.0'C
            temp_str = result.stdout.strip()
            temp = float(temp_str.replace("temp=", "").replace("'C", ""))
            return temp
        except Exception:
            return None

    def check_thermal(self) -> None:
        """Verifica temperatura e ajusta se necessário."""
        temp = self._get_temperature()
        if temp is None:
            return

        if temp >= self.temp_threshold_critical:
            if self._current_mode != PowerMode.ULTRA_POWER_SAVE:
                logger.warning(f"Temperatura crítica: {temp}°C. Reduzindo para ultra power save.")
                self.set_mode(PowerMode.ULTRA_POWER_SAVE)
                self._thermal_throttled = True

        elif temp >= self.temp_threshold_high:
            if self._current_mode == PowerMode.PERFORMANCE:
                logger.warning(f"Temperatura alta: {temp}°C. Reduzindo para power save.")
                self.set_mode(PowerMode.POWER_SAVE)
                self._thermal_throttled = True

        elif self._thermal_throttled and temp < self.temp_threshold_high - 10:
            # Temperatura normalizou, restaurar modo
            logger.info(f"Temperatura normalizada: {temp}°C. Restaurando modo.")
            self.set_mode(self.default_mode)
            self._thermal_throttled = False

    def _idle_monitor(self) -> None:
        """Thread de monitoramento (extendida com thermal)."""
        while not self._stop_event.is_set():
            if self.auto_adjust:
                # Verificar idle
                idle_time = time.time() - self._last_activity
                if idle_time >= self.idle_timeout and not self._is_idle:
                    self._is_idle = True
                    logger.info(f"Entrando em modo idle após {idle_time:.0f}s")
                    self.set_mode(self.idle_mode)

                # Verificar temperatura
                self.check_thermal()

            self._stop_event.wait(10)
