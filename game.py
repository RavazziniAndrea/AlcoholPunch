import pygame
import math
import serial
import threading
import time
import random
import colorsys
from typing import Optional

# Importa GPIO per Raspberry Pi (con fallback per test su PC)
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    print("GPIO di Raspberry Pi disponibile")
except ImportError:
    GPIO_AVAILABLE = False
    print("GPIO non disponibile - modalità test attivata (usa SPAZIO per simulare il pulsante)")

# Inizializzazione pygame
pygame.init()

# Costanti
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
FPS = 60

# Pin GPIO per il pulsante (modifica secondo il tuo setup)
BUTTON_PIN = 18

# Colori
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
BLUE = (0, 100, 255)
DARK_GRAY = (40, 40, 40)
LIGHT_GRAY = (200, 200, 200)
NEON_GREEN = (57, 255, 20)
NEON_RED = (255, 16, 16)
NEON_YELLOW = (255, 255, 16)


class ParticleEffect:
    def __init__(self, x, y, color, speed=2):
        self.x = x
        self.y = y
        self.color = color
        self.speed = speed
        self.life = 255
        self.size = random.randint(2, 5)
        self.vel_x = random.uniform(-1, 1) * speed
        self.vel_y = random.uniform(-2, -0.5) * speed

    def update(self):
        self.x += self.vel_x
        self.y += self.vel_y
        self.life -= 3
        self.size = max(1, self.size - 0.1)
        return self.life > 0

    def draw(self, screen):
        if self.life > 0:
            alpha = max(0, self.life)
            color_with_alpha = (*self.color[:3], alpha)
            temp_surface = pygame.Surface(
                (self.size * 2, self.size * 2), pygame.SRCALPHA
            )
            pygame.draw.circle(
                temp_surface, color_with_alpha, (self.size, self.size), int(self.size)
            )
            screen.blit(temp_surface, (self.x - self.size, self.y - self.size))


class AlcoholMeter:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Alcohol test Barboun")
        self.clock = pygame.time.Clock()
        self.running = True

        # Stati del sistema
        self.STATE_WAITING = 0      # Schermata iniziale - aspetta il pulsante
        self.STATE_INSTRUCTIONS = 1  # Mostra istruzioni per 10 secondi
        self.STATE_READING = 2      # Sta leggendo il valore alcolico
        self.STATE_RESULT = 3       # Mostra il risultato finale
        
        self.current_state = self.STATE_WAITING
        self.state_timer = 0
        
        # Durate degli stati (in frames a 60 FPS)
        self.instructions_duration = 300  # 10 secondi
        self.reading_duration = 300       # 5 secondi  
        self.result_duration = 300        # 5 secondi

        # Variabili per il valore alcolico
        self.current_value = 0.0
        self.target_value = 0.0
        self.max_value = 2.5
        self.max_reached_value = 0.0  # Valore massimo raggiunto

        # Animazioni
        self.needle_angle = 180  # Inizia a sinistra (180°) per mezzaluna orizzontale
        self.target_angle = 180
        self.glow_intensity = 0
        self.glow_direction = 1
        self.pulse_time = 0
        self.result_scale = 1.0  # Scala per l'animazione del risultato finale
        self.result_glow = 0

        # Animazione per la schermata iniziale
        self.waiting_pulse = 0
        self.button_pressed = False

        # Particelle
        self.particles = []

        # Setup GPIO
        self.setup_gpio()

        # Comunicazione seriale (commentata per test)
        self.ser = None
        self.serial_thread = None
        self.setup_serial()

        # Font - includi font digitali se disponibili
        try:
            # Prova a caricare un font digitale/monospace
            self.font_digital_large = pygame.font.Font("digital-7.ttf", 96)
            self.font_digital_medium = pygame.font.Font("digital-7.ttf", 64)
        except:
            # Fallback su font di sistema
            self.font_digital_large = pygame.font.Font(None, 96)
            self.font_digital_medium = pygame.font.Font(None, 64)

        self.font_large = pygame.font.Font(None, 72)
        self.font_medium = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 32)
        self.font_extra_large = pygame.font.Font(None, 120)

        # Centro del tachimetro (mezzaluna orizzontale)
        self.center_x = SCREEN_WIDTH // 2
        self.center_y = SCREEN_HEIGHT // 2 + 100
        self.radius = 250

        # Lista di istruzioni (puoi personalizzare)
        self.instructions = [
            "1. Mettiti a 10-15cm dal buco",
            "2. Soffia per circa 5 secondi",
            "3. Aspetta che appaia il risultato finale",
            "",
            "",
            "-- Questo è un gioco, non è preciso --",
        ]

    def setup_gpio(self):
        global GPIO_AVAILABLE
        """Configura i pin GPIO del Raspberry Pi"""
        if GPIO_AVAILABLE:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                # Aggiungi callback per il pulsante (fronte di discesa)
                GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, 
                                    callback=self.button_callback, bouncetime=300)
                print(f"GPIO setup completato - Pulsante su pin {BUTTON_PIN}")
            except Exception as e:
                print(f"Errore setup GPIO: {e}")
                GPIO_AVAILABLE = False

    def button_callback(self, channel):
        """Callback chiamata quando il pulsante viene premuto"""
        if self.current_state == self.STATE_WAITING:
            self.button_pressed = True
            print("Pulsante premuto - avvio test")

    def setup_serial(self):
        """Configura la comunicazione seriale"""
        try:
            # Sostituisci 'COM3' con la porta corretta del tuo dispositivo
            # Su Linux/Mac potrebbe essere '/dev/ttyUSB0' or '/dev/ttyACM0'
            self.ser = serial.Serial("COM3", 9600, timeout=1)
            self.serial_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.serial_thread.start()
            print("Connessione seriale stabilita")
        except Exception as e:
            print(f"Errore connessione seriale: {e}")
            print("Modalità demo attivata - usa i tasti freccia per testare")

    def read_serial(self):
        """Legge i dati dalla porta seriale"""
        while self.running and self.ser:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode("utf-8").strip()
                    try:
                        value = float(line)
                        if 0 <= value <= self.max_value:
                            self.target_value = value
                    except ValueError:
                        pass
            except Exception as e:
                print(f"Errore lettura seriale: {e}")
            time.sleep(0.1)

    def update_state_machine(self):
        """Gestisce la macchina a stati"""
        if self.current_state == self.STATE_WAITING:
            # Aspetta che il pulsante venga premuto
            if self.button_pressed:
                self.current_state = self.STATE_INSTRUCTIONS
                self.state_timer = 0
                self.button_pressed = False
                
        elif self.current_state == self.STATE_INSTRUCTIONS:
            # Mostra istruzioni per 10 secondi
            self.state_timer += 1
            if self.state_timer >= self.instructions_duration:
                self.current_state = self.STATE_READING
                self.state_timer = 0
                # Reset valori per la nuova lettura
                self.current_value = 0.0
                self.target_value = 0.0
                self.max_reached_value = 0.0
                
        elif self.current_state == self.STATE_READING:
            # Fase di lettura per 5 secondi
            self.state_timer += 1
            if self.state_timer >= self.reading_duration:
                self.current_state = self.STATE_RESULT
                self.state_timer = 0
                # Imposta il valore finale al massimo raggiunto
                self.current_value = self.max_reached_value
                
        elif self.current_state == self.STATE_RESULT:
            # Mostra risultato per 5 secondi
            self.state_timer += 1
            if self.state_timer >= self.result_duration:
                # Torna alla schermata iniziale
                self.current_state = self.STATE_WAITING
                self.state_timer = 0
                self.waiting_pulse = 0

    def update_values(self):
        """Aggiorna i valori con animazioni fluide"""
        self.update_state_machine()
        
        if self.current_state == self.STATE_READING:
            # Solo durante la lettura aggiorna i valori
            # Interpolazione fluida del valore corrente
            diff = self.target_value - self.current_value
            self.current_value += diff * 0.1

            # Aggiorna il valore massimo raggiunto durante la lettura
            if self.current_value > self.max_reached_value:
                self.max_reached_value = self.current_value
                
        elif self.current_state == self.STATE_RESULT:
            # Mantieni il valore al massimo raggiunto
            self.current_value = self.max_reached_value

        # Calcola l'angolo della freccia (da 180° a 0° per mezzaluna orizzontale)
        progress = self.current_value / self.max_value
        self.target_angle = 180 - (progress * 180)  # Da sinistra (180°) a destra (0°)

        # Interpolazione fluida dell'angolo
        angle_diff = self.target_angle - self.needle_angle
        self.needle_angle += angle_diff * 0.15

        # Animazioni varie
        if self.current_state == self.STATE_RESULT:
            self.result_scale = 1.0 + 0.3 * abs(math.sin(self.pulse_time * 3))
            self.result_glow = 50 + 80 * abs(math.sin(self.pulse_time * 4))
        else:
            self.result_scale = 1.0
            self.result_glow = 0

        # Aggiorna effetti
        self.pulse_time += 0.1
        self.waiting_pulse += 0.05
        self.glow_intensity += self.glow_direction * 5
        if self.glow_intensity >= 100:
            self.glow_direction = -1
        elif self.glow_intensity <= 0:
            self.glow_direction = 1

    def add_particles(self):
        """Aggiunge particelle in base al livello alcolico"""
        if self.current_state == self.STATE_READING and self.current_value > 0.5:
            num_particles = int(self.current_value * 3)
            for _ in range(num_particles):
                x = self.center_x + random.randint(-50, 50)
                y = self.center_y + random.randint(-30, 30)

                if self.current_value < 1.0:
                    color = NEON_YELLOW
                elif self.current_value < 2.0:
                    color = ORANGE
                else:
                    color = NEON_RED

                self.particles.append(ParticleEffect(x, y, color))

    def update_particles(self):
        """Aggiorna le particelle"""
        self.particles = [p for p in self.particles if p.update()]

    def get_status_color(self):
        """Restituisce il colore in base al livello alcolico"""
        value_to_check = self.current_value
        if self.current_state == self.STATE_RESULT:
            value_to_check = self.max_reached_value

        if value_to_check < 0.5:
            return NEON_GREEN
        elif value_to_check < 1.5:
            return NEON_YELLOW
        elif value_to_check < 2.0:
            return ORANGE
        else:
            return NEON_RED

    def get_status_text(self):
        """Restituisce il testo dello stato"""
        if self.current_state == self.STATE_RESULT:
            if self.max_reached_value < 0.5:
                return "SOBRIO"
            elif self.max_reached_value < 1.5:
                return "ATTENZIONE"
            elif self.max_reached_value < 2.0:
                return "ALTERATO"
            else:
                return "PERICOLOSO"
        else:
            return "LETTURA IN CORSO..."

    def draw_background(self):
        """Disegna lo sfondo con effetti"""
        # Gradiente di sfondo
        for y in range(SCREEN_HEIGHT):
            ratio = y / SCREEN_HEIGHT
            r = int(20 + ratio * 20)
            g = int(25 + ratio * 25)
            b = int(40 + ratio * 30)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (SCREEN_WIDTH, y))

        # Effetto pulse di sfondo
        if self.current_value > 1.0 and self.current_state in [self.STATE_READING, self.STATE_RESULT]:
            pulse = abs(math.sin(self.pulse_time)) * 30
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            color = (*self.get_status_color()[:3], int(pulse))
            overlay.fill(color)
            self.screen.blit(overlay, (0, 0))

    def cycle_colors_hsv(t, speed=0.02):
        h = (t * speed) % 1.0   # Hue da 0 a 1
        r, g, b = colorsys.hsv_to_rgb(h, 1, 1)
        return int(r*255), int(g*255), int(b*255)
    
    def draw_waiting_screen(self):
        """Disegna la schermata di attesa iniziale"""
        # Titolo principale
        title_surface = self.font_extra_large.render("Alcohol test Barboun", True, WHITE)
        title_rect = title_surface.get_rect(center=(self.center_x, 200))
        self.screen.blit(title_surface, title_rect)

        # Messaggio pulsante con effetto pulsante
        pulse_alpha = int(128 + 127 * abs(math.sin(self.waiting_pulse * 1)))
        r, g, b = AlcoholMeter.cycle_colors_hsv(self.waiting_pulse, speed=0.05)  # speed regola la velocità del ciclo
        button_color = (r, g, b, pulse_alpha)
        #button_color = (*NEON_GREEN[:3], pulse_alpha)
        
        button_text = "PREMI IL PULSANTE PER INIZIARE"
        button_surface = self.font_large.render(button_text, True, WHITE)
        button_rect = button_surface.get_rect(center=(self.center_x, self.center_y))
        
        # Sfondo pulsante con glow
        glow_rect = pygame.Rect(button_rect.x - 50, button_rect.y - 30, 
                               button_rect.width + 100, button_rect.height + 60)
        glow_surface = pygame.Surface((glow_rect.width, glow_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(glow_surface, button_color, (0, 0, glow_rect.width, glow_rect.height), 
                        border_radius=30)
        self.screen.blit(glow_surface, (glow_rect.x, glow_rect.y))
        
        # Bordo del pulsante
        pygame.draw.rect(self.screen, NEON_GREEN, glow_rect, 5, border_radius=30)
        
        # Testo del pulsante
        self.screen.blit(button_surface, button_rect)

        # Istruzioni in piccolo in basso
        if not GPIO_AVAILABLE:
            demo_text = "MODALITÀ DEMO - Premi SPAZIO per simulare il pulsante"
            demo_surface = self.font_small.render(demo_text, True, LIGHT_GRAY)
            demo_rect = demo_surface.get_rect(center=(self.center_x, SCREEN_HEIGHT - 50))
            self.screen.blit(demo_surface, demo_rect)

    def draw_instructions_screen(self):
        """Disegna la schermata delle istruzioni"""
        # Titolo
        title_surface = self.font_large.render("ISTRUZIONI PER L'USO", True, WHITE)
        title_rect = title_surface.get_rect(center=(self.center_x, 120))
        self.screen.blit(title_surface, title_rect)

        # Box delle istruzioni
        box_width = 800
        box_height = 400
        box_x = (SCREEN_WIDTH - box_width) // 2
        box_y = 200
        
        # Sfondo del box
        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
        pygame.draw.rect(self.screen, (30, 30, 60), box_rect, border_radius=20)
        pygame.draw.rect(self.screen, NEON_YELLOW, box_rect, 5, border_radius=20)

        # Disegna le istruzioni
        y_offset = box_y + 50
        for i, instruction in enumerate(self.instructions):
            instruction_surface = self.font_medium.render(instruction, True, WHITE)
            instruction_rect = instruction_surface.get_rect(center=(self.center_x, y_offset + i * 60))
            self.screen.blit(instruction_surface, instruction_rect)

        # Timer countdown
        remaining_time = max(0, (self.instructions_duration - self.state_timer) / 60)
        timer_text = f"Il test inizierà tra: {remaining_time:.1f}s"
        timer_surface = self.font_medium.render(timer_text, True, NEON_GREEN)
        timer_rect = timer_surface.get_rect(center=(self.center_x, box_y + box_height + 50))
        self.screen.blit(timer_surface, timer_rect)

    def draw_gauge(self):
        """Disegna il tachimetro a mezzaluna orizzontale"""
        if self.current_state not in [self.STATE_READING, self.STATE_RESULT]:
            return
            
        # Effetto glow per l'arco
        glow_radius = self.radius + 30
        glow_surface = pygame.Surface(
            (glow_radius * 2, glow_radius * 2), pygame.SRCALPHA
        )
        glow_color = (*self.get_status_color()[:3], 50 + self.glow_intensity)

        # Disegna solo l'arco superiore per il glow
        pygame.draw.arc(
            glow_surface,
            glow_color,
            (0, 0, glow_radius * 2, glow_radius * 2),
            0,
            math.pi,
            20,
        )
        self.screen.blit(
            glow_surface, (self.center_x - glow_radius, self.center_y - glow_radius)
        )

        # Arco della mezzaluna (solo semicerchio superiore)
        gauge_rect = pygame.Rect(
            self.center_x - self.radius,
            self.center_y - self.radius,
            self.radius * 2,
            self.radius * 2,
        )

        # Sfondo dell'arco - solo parte superiore
        pygame.draw.arc(self.screen, DARK_GRAY, gauge_rect, 0, math.pi, 15)

        # Arco interno nero
        pygame.draw.arc(self.screen, BLACK, gauge_rect, 0, math.pi, 8)

        # Bordi laterali per chiudere la mezzaluna
        left_x = self.center_x - self.radius
        right_x = self.center_x + self.radius
        pygame.draw.line(
            self.screen,
            DARK_GRAY,
            (left_x, self.center_y),
            (left_x + 15, self.center_y),
            8,
        )
        pygame.draw.line(
            self.screen,
            DARK_GRAY,
            (right_x - 15, self.center_y),
            (right_x, self.center_y),
            8,
        )

        # Segni del tachimetro lungo l'arco superiore
        for i in range(11):  # 0 a 2.5 con step di 0.25
            # Angolo da 180° (sinistra) a 0° (destra) solo nella parte superiore
            angle = math.radians(180 - (i * 18))  # Da 180° a 0° (18° = 180°/10)
            value = i * 0.25

            # Colore del segno
            if value < 0.5:
                color = GREEN
            elif value < 1.5:
                color = YELLOW
            elif value < 2.0:
                color = ORANGE
            else:
                color = RED

            # Linee dei segni - solo nella parte superiore (sin(angle) >= 0)
            if math.sin(angle) >= 0:
                start_x = self.center_x + math.cos(angle) * (self.radius - 40)
                start_y = self.center_y - math.sin(angle) * (self.radius - 40)
                end_x = self.center_x + math.cos(angle) * (self.radius - 15)
                end_y = self.center_y - math.sin(angle) * (self.radius - 15)

                pygame.draw.line(
                    self.screen, color, (start_x, start_y), (end_x, end_y), 5
                )

                # Numeri - solo per valori pari e nella parte superiore
                if i % 2 == 0:
                    text = self.font_small.render(f"{value:.1f}", True, WHITE)
                    text_x = (
                        self.center_x
                        + math.cos(angle) * (self.radius - 60)
                        - text.get_width() // 2
                    )
                    text_y = (
                        self.center_y
                        - math.sin(angle) * (self.radius - 60)
                        - text.get_height() // 2
                    )
                    self.screen.blit(text, (text_x, text_y))

    def draw_needle(self):
        """Disegna la freccia del tachimetro"""
        if self.current_state not in [self.STATE_READING, self.STATE_RESULT]:
            return
            
        angle_rad = math.radians(self.needle_angle)
        needle_length = self.radius - 50

        # Assicurati che la freccia rimanga nella parte superiore della mezzaluna
        # Limita l'angolo tra 0° e 180° (solo parte superiore)
        clamped_angle = max(0, min(180, self.needle_angle))
        angle_rad = math.radians(clamped_angle)

        # Punta della freccia
        tip_x = self.center_x + math.cos(angle_rad) * needle_length
        tip_y = self.center_y - math.sin(angle_rad) * needle_length

        # Base della freccia (più larga)
        base_width = 20
        base_length = 40

        # Calcola i punti della freccia
        # Punto centrale della base
        base_x = self.center_x + math.cos(angle_rad) * base_length
        base_y = self.center_y - math.sin(angle_rad) * base_length

        # Angolo perpendicolare per la larghezza
        perp_angle = angle_rad - math.pi / 2

        # Punti della base della freccia
        base_left_x = base_x + math.cos(perp_angle) * (base_width / 2)
        base_left_y = base_y + math.sin(perp_angle) * (base_width / 2)
        base_right_x = base_x - math.cos(perp_angle) * (base_width / 2)
        base_right_y = base_y - math.sin(perp_angle) * (base_width / 2)

        # Punti per la forma della freccia
        arrow_points = [
            (tip_x, tip_y),  # Punta
            (base_left_x, base_left_y),  # Base sinistra
            (base_right_x, base_right_y),  # Base destra
        ]

        # Disegna la freccia con effetto glow
        needle_color = self.get_status_color()

        # Effetto glow della freccia
        glow_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for i in range(5):
            glow_color = (*needle_color[:3], 30 - i * 5)
            if len(arrow_points) >= 3:
                # Espandi leggermente i punti per il glow
                expanded_points = []
                for px, py in arrow_points:
                    # Calcola la direzione dal centro per espandere
                    dx = px - self.center_x
                    dy = py - self.center_y
                    length = math.sqrt(dx * dx + dy * dy)
                    if length > 0:
                        expansion = i * 1.5
                        expanded_points.append(
                            (
                                px + (dx / length) * expansion,
                                py + (dy / length) * expansion,
                            )
                        )
                    else:
                        expanded_points.append((px, py))
                pygame.draw.polygon(glow_surface, glow_color, expanded_points)
        self.screen.blit(glow_surface, (0, 0))

        # Freccia principale
        pygame.draw.polygon(self.screen, needle_color, arrow_points)
        pygame.draw.polygon(self.screen, WHITE, arrow_points, 2)

        # Centro della freccia
        pygame.draw.circle(
            self.screen, needle_color, (self.center_x, self.center_y), 12
        )
        pygame.draw.circle(self.screen, WHITE, (self.center_x, self.center_y), 6)

    def draw_display(self):
        """Disegna il display digitale"""
        if self.current_state not in [self.STATE_READING, self.STATE_RESULT]:
            return
            
        # Display principale
        display_y = self.center_y + 120

        if self.current_state == self.STATE_READING:
            # FASE DI LETTURA - Mostra valore corrente
            current_color = self.get_status_color()

            # Formatta il numero con 2 decimali
            value_text = f"{self.current_value:.2f}"
            value_surface = self.font_digital_large.render(
                value_text, True, current_color
            )
            value_rect = value_surface.get_rect(center=(self.center_x, display_y + 30))

            # Sfondo del display
            display_rect = pygame.Rect(
                value_rect.x - 30,
                value_rect.y - 20,
                value_rect.width + 60,
                value_rect.height + 40,
            )
            pygame.draw.rect(self.screen, BLACK, display_rect, border_radius=15)
            pygame.draw.rect(
                self.screen, current_color, display_rect, 4, border_radius=15
            )

            # Valore corrente
            self.screen.blit(value_surface, value_rect)

            # Timer di lettura
            remaining_time = max(0, (self.reading_duration - self.state_timer) / 60)
            timer_text = f"Tempo: {remaining_time:.1f}s"
            timer_surface = self.font_small.render(timer_text, True, WHITE)
            timer_rect = timer_surface.get_rect(center=(self.center_x, display_y - 30))
            self.screen.blit(timer_surface, timer_rect)

        else:
            # FASE RISULTATO - Mostra valore massimo con animazioni
            result_color = self.get_status_color()
            scale_factor = self.result_scale

            # Font scalato per l'effetto pulsante
            scaled_font_size = int(96 * scale_factor)
            try:
                scaled_font = pygame.font.Font("digital-7.ttf", scaled_font_size)
            except:
                scaled_font = pygame.font.Font(None, scaled_font_size)

            # Formatta il valore massimo
            max_value_text = f"{self.max_reached_value:.2f}"
            max_value_surface = scaled_font.render(max_value_text, True, result_color)
            max_value_rect = max_value_surface.get_rect(
                center=(self.center_x, display_y + 30)
            )

            # Effetto glow pulsante
            glow_alpha = int(self.result_glow)
            if glow_alpha > 0:
                glow_surface = pygame.Surface(
                    (max_value_rect.width + 150, max_value_rect.height + 100),
                    pygame.SRCALPHA,
                )
                glow_color = (*result_color[:3], glow_alpha)
                pygame.draw.rect(
                    glow_surface,
                    glow_color,
                    (0, 0, max_value_rect.width + 150, max_value_rect.height + 100),
                    border_radius=30,
                )
                self.screen.blit(
                    glow_surface, (max_value_rect.x - 75, max_value_rect.y - 50)
                )

            # Sfondo del display risultato (più spesso e colorato)
            result_display_rect = pygame.Rect(
                max_value_rect.x - 50,
                max_value_rect.y - 30,
                max_value_rect.width + 100,
                max_value_rect.height + 60,
            )
            pygame.draw.rect(self.screen, BLACK, result_display_rect, border_radius=20)
            pygame.draw.rect(
                self.screen, result_color, result_display_rect, 8, border_radius=20
            )

            # Valore massimo raggiunto
            self.screen.blit(max_value_surface, max_value_rect)

            # Timer per il prossimo ciclo
            remaining_time = max(0, (self.result_duration - self.state_timer) / 60)
            timer_text = f"Nuovo test in: {remaining_time:.1f}s"
            timer_surface = self.font_small.render(timer_text, True, WHITE)
            timer_rect = timer_surface.get_rect(center=(self.center_x, display_y - 40))
            self.screen.blit(timer_surface, timer_rect)

        # Unità di misura (sempre presente)
        unit_text = "‰ BAC"
        unit_surface = self.font_small.render(unit_text, True, WHITE)
        unit_rect = unit_surface.get_rect(center=(self.center_x, display_y + 90))
        self.screen.blit(unit_surface, unit_rect)

    def draw_status(self):
        """Disegna lo status e le informazioni"""
        if self.current_state not in [self.STATE_READING, self.STATE_RESULT]:
            return
            
        # Status text
        status_text = self.get_status_text()
        status_surface = self.font_medium.render(
            status_text, True, self.get_status_color()
        )
        status_rect = status_surface.get_rect(center=(self.center_x, 100))
        self.screen.blit(status_surface, status_rect)

        # Titolo
        title_surface = self.font_large.render("ETILOMETRO DIGITALE", True, WHITE)
        title_rect = title_surface.get_rect(center=(self.center_x, 50))
        self.screen.blit(title_surface, title_rect)

        # Istruzioni (se in modalità demo)
        if not self.ser:
            demo_text = "MODALITÀ DEMO - Usa frecce SU/GIÙ per testare"
            demo_surface = self.font_small.render(demo_text, True, LIGHT_GRAY)
            demo_rect = demo_surface.get_rect(
                center=(self.center_x, SCREEN_HEIGHT - 30)
            )
            self.screen.blit(demo_surface, demo_rect)

    def handle_events(self):
        """Gestisce gli eventi"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                # Simulazione pulsante GPIO con SPAZIO se non c'è GPIO
                if event.key == pygame.K_SPACE and not GPIO_AVAILABLE:
                    if self.current_state == self.STATE_WAITING:
                        self.button_pressed = True
                        
                # Test con tastiera se non c'è seriale (solo durante la lettura)
                if not self.ser and self.current_state == self.STATE_READING:
                    if event.key == pygame.K_UP:
                        self.target_value = min(self.max_value, self.target_value + 0.1)
                    elif event.key == pygame.K_DOWN:
                        self.target_value = max(0, self.target_value - 0.1)
                    elif event.key == pygame.K_r:
                        self.target_value = 0
                        self.max_reached_value = 0
                        
                if event.key == pygame.K_ESCAPE:
                    self.running = False

    def cleanup(self):
        """Pulizia delle risorse"""
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
                print("GPIO cleanup completato")
            except Exception as e:
                print(f"Errore durante GPIO cleanup: {e}")
        
        if self.ser:
            self.ser.close()

    def run(self):
        """Loop principale"""
        try:
            while self.running:
                self.handle_events()
                self.update_values()
                self.add_particles()
                self.update_particles()

                # Disegna lo sfondo
                self.draw_background()

                # Disegna la schermata appropriata in base allo stato
                if self.current_state == self.STATE_WAITING:
                    self.draw_waiting_screen()
                elif self.current_state == self.STATE_INSTRUCTIONS:
                    self.draw_instructions_screen()
                elif self.current_state in [self.STATE_READING, self.STATE_RESULT]:
                    self.draw_gauge()
                    self.draw_needle()
                    self.draw_display()
                    self.draw_status()

                # Disegna particelle (solo durante lettura/risultato)
                if self.current_state in [self.STATE_READING, self.STATE_RESULT]:
                    for particle in self.particles:
                        particle.draw(self.screen)

                pygame.display.flip()
                self.clock.tick(FPS)

        except KeyboardInterrupt:
            print("\nInterrotto dall'utente")
        finally:
            self.cleanup()
            pygame.quit()


if __name__ == "__main__":
    app = AlcoholMeter()
    app.run()
    GPIO_AVAILABLE = True
    app.run()