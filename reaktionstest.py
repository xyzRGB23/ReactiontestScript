import csv
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class ReactionTestApp:
    SESSION_GAP_SECONDS = 60 * 60
    ROLLING_WINDOW = 5
    TARGET_RADIUS_PX = 28

    FIELDNAMES = [
        "timestamp",
        "mode",
        "reaction_ms",
        "attempts_to_hit",
        "mean_miss_px",
        "last_miss_px",
        "hit_offset_px",
        "target_x_px",
        "target_y_px",
        "canvas_width_px",
        "canvas_height_px",
        "hit_radius_px",
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("Reaktionstest")
        self.root.geometry("1250x850")
        self.root.minsize(980, 700)

        self.data_file = Path(__file__).with_name("reaction_results_multimode.csv")
        self.legacy_file = Path(__file__).with_name("reaction_results.csv")

        self.records = []

        self.classic_waiting_for_green = False
        self.classic_ready_to_click = False
        self.classic_start_time = None
        self.classic_timer_id = None

        self.target_waiting = False
        self.target_active = False
        self.target_start_time = None
        self.target_timer_id = None
        self.target_center = None
        self.target_radius = self.TARGET_RADIUS_PX
        self.target_attempts = 0
        self.target_miss_distances = []

        self.metric_specs = {
            "Klassisch: Reaktionszeit [ms]": {
                "mode": "classic",
                "field": "reaction_ms",
                "unit": "ms",
                "title": "Klassischer Modus: Reaktionszeit",
            },
            "Zielkreis: Reaktionszeit [ms]": {
                "mode": "target",
                "field": "reaction_ms",
                "unit": "ms",
                "title": "Zielkreis-Modus: Reaktionszeit bis Treffer",
            },
            "Zielkreis: Versuche bis Treffer": {
                "mode": "target",
                "field": "attempts_to_hit",
                "unit": "Versuche",
                "title": "Zielkreis-Modus: Anzahl der Klickversuche bis Treffer",
            },
            "Zielkreis: mittlere Abweichung [px]": {
                "mode": "target",
                "field": "mean_miss_px",
                "unit": "px",
                "title": "Zielkreis-Modus: mittlere Abweichung der Fehlklicks",
            },
            "Zielkreis: letzter Fehlklick [px]": {
                "mode": "target",
                "field": "last_miss_px",
                "unit": "px",
                "title": "Zielkreis-Modus: Abstand des letzten Fehlklicks vom Kreisrand",
            },
            "Zielkreis: Treffer-Abstand vom Mittelpunkt [px]": {
                "mode": "target",
                "field": "hit_offset_px",
                "unit": "px",
                "title": "Zielkreis-Modus: Abstand des Treffers vom Kreismittelpunkt",
            },
        }

        self.load_results()
        self.build_gui()
        self.update_stats()
        self.update_graph()

    # ---------- GUI ----------

    def build_gui(self):
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.classic_frame = tk.Frame(self.notebook, height=150)
        self.target_frame = tk.Frame(self.notebook, height=320)

        self.notebook.add(self.classic_frame, text="Klassischer Modus")
        self.notebook.add(self.target_frame, text="Zielkreis-Modus")

        self.build_classic_tab()
        self.build_target_tab()
        self.build_analysis_area()

    def build_classic_tab(self):
        self.classic_frame.grid_columnconfigure(0, weight=1)

        self.classic_info_label = tk.Label(
            self.classic_frame,
            text="Start drücken. Wenn das Feld grün wird, sofort klicken.",
            font=("Arial", 12)
        )
        self.classic_info_label.grid(row=0, column=0, sticky="ew", pady=(6, 4))

        self.classic_click_area = tk.Button(
            self.classic_frame,
            text="Start",
            font=("Arial", 30, "bold"),
            bg="#dddddd",
            activebackground="#dddddd",
            height=5,
            command=self.handle_classic_click
        )
        self.classic_click_area.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 12))

    def build_target_tab(self):
        self.target_frame.grid_rowconfigure(1, weight=1)
        self.target_frame.grid_columnconfigure(0, weight=1)

        self.target_info_label = tk.Label(
            self.target_frame,
            text="Start drücken. Nach kurzer Wartezeit erscheint ein Zielkreis an zufälliger Position.",
            font=("Arial", 12)
        )
        self.target_info_label.grid(row=0, column=0, sticky="ew", pady=(6, 4))

        self.target_canvas = tk.Canvas(
            self.target_frame,
            height=260,
            bg="#dddddd",
            highlightthickness=1,
            highlightbackground="#999999"
        )
        self.target_canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=4)
        self.target_canvas.bind("<Button-1>", self.handle_target_canvas_click)

        self.target_button_frame = tk.Frame(self.target_frame)
        self.target_button_frame.grid(row=2, column=0, pady=(4, 8))

        self.target_start_button = tk.Button(
            self.target_button_frame,
            text="Zielversuch starten",
            command=self.start_target_trial
        )
        self.target_start_button.grid(row=0, column=0, padx=8)

        self.target_cancel_button = tk.Button(
            self.target_button_frame,
            text="Zielversuch abbrechen",
            command=self.cancel_target_trial
        )
        self.target_cancel_button.grid(row=0, column=1, padx=8)

        self.root.after(100, lambda: self.draw_canvas_message("Start drücken, dann Zielkreis treffen."))

    def build_analysis_area(self):
        analysis_frame = tk.Frame(self.root)
        analysis_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        analysis_frame.grid_rowconfigure(0, weight=1)
        analysis_frame.grid_columnconfigure(0, weight=1)
        analysis_frame.grid_columnconfigure(1, weight=0)

        graph_frame = tk.Frame(analysis_frame)
        graph_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        graph_frame.grid_rowconfigure(1, weight=1)
        graph_frame.grid_columnconfigure(0, weight=1)

        graph_select_frame = tk.Frame(graph_frame)
        graph_select_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        graph_select_frame.grid_columnconfigure(1, weight=1)

        tk.Label(graph_select_frame, text="Graph:", font=("Arial", 11)).grid(row=0, column=0, padx=(0, 6))

        self.graph_metric_var = tk.StringVar(value="Klassisch: Reaktionszeit [ms]")
        self.graph_metric_box = ttk.Combobox(
            graph_select_frame,
            textvariable=self.graph_metric_var,
            values=list(self.metric_specs.keys()),
            state="readonly"
        )
        self.graph_metric_box.grid(row=0, column=1, sticky="ew")
        self.graph_metric_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_analysis())

        self.fig = Figure(figsize=(9.5, 5.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        side_frame = tk.Frame(analysis_frame, width=280)
        side_frame.grid(row=0, column=1, sticky="ns")
        side_frame.grid_propagate(False)
        side_frame.grid_columnconfigure(0, weight=1)

        button_frame = tk.LabelFrame(side_frame, text="Steuerung", padx=8, pady=8)
        button_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        button_frame.grid_columnconfigure(0, weight=1)

        self.reset_button = tk.Button(button_frame, text="Alle Ergebnisse löschen", command=self.reset_results)
        self.reset_button.grid(row=0, column=0, sticky="ew", pady=3)

        self.export_button = tk.Button(button_frame, text="CSV exportieren", command=self.export_csv)
        self.export_button.grid(row=1, column=0, sticky="ew", pady=3)

        self.info_button = tk.Button(button_frame, text="Auswertung erklären", command=self.show_analysis_info)
        self.info_button.grid(row=2, column=0, sticky="ew", pady=3)

        stats_frame = tk.LabelFrame(side_frame, text="Statistik zur Graph-Auswahl", padx=8, pady=8)
        stats_frame.grid(row=1, column=0, sticky="ew")
        stats_frame.grid_columnconfigure(0, weight=1)

        self.count_label = tk.Label(stats_frame, text="Messungen: 0", anchor="w", font=("Arial", 11))
        self.count_label.grid(row=0, column=0, sticky="ew", pady=2)

        self.mean_label = tk.Label(stats_frame, text="Gesamt-Mittelwert: –", anchor="w", font=("Arial", 11))
        self.mean_label.grid(row=1, column=0, sticky="ew", pady=2)

        self.std_label = tk.Label(stats_frame, text="Gesamt-s: –", anchor="w", font=("Arial", 11))
        self.std_label.grid(row=2, column=0, sticky="ew", pady=2)

        self.session_label = tk.Label(stats_frame, text="Aktuelle Session: –", anchor="w", justify="left", wraplength=245, font=("Arial", 11))
        self.session_label.grid(row=3, column=0, sticky="ew", pady=(10, 2))

        self.session_mean_label = tk.Label(stats_frame, text="Session-Mittelwert: –", anchor="w", font=("Arial", 11))
        self.session_mean_label.grid(row=4, column=0, sticky="ew", pady=2)

        self.session_std_label = tk.Label(stats_frame, text="Session-s: –", anchor="w", font=("Arial", 11))
        self.session_std_label.grid(row=5, column=0, sticky="ew", pady=2)

        #hint_frame = tk.LabelFrame(side_frame, text="Hinweis", padx=8, pady=8)
        #hint_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        #self.hint_label = tk.Label(
        #    hint_frame,
        #    text="Der Graph nutzt die links ausgewählte Messgröße. Die Statistik rechts gehört immer zu dieser Auswahl.",
        #    anchor="w",
        #    justify="left",
        #    wraplength=245
        #)
        #self.hint_label.grid(row=0, column=0, sticky="ew")

    def on_tab_changed(self, event=None):
        tab_text = self.notebook.tab(self.notebook.select(), "text")

        if tab_text == "Klassischer Modus":
            self.graph_metric_var.set("Klassisch: Reaktionszeit [ms]")
        else:
            self.graph_metric_var.set("Zielkreis: Reaktionszeit [ms]")

        self.refresh_analysis()

    def refresh_analysis(self):
        self.update_stats()
        self.update_graph()

    # ---------- Klassischer Modus ----------

    def handle_classic_click(self):
        if not self.classic_waiting_for_green and not self.classic_ready_to_click:
            self.start_classic_trial()
        elif self.classic_waiting_for_green:
            self.classic_too_early()
        elif self.classic_ready_to_click:
            self.record_classic_reaction()

    def start_classic_trial(self):
        delay_ms = random.randint(1000, 10000)

        self.classic_waiting_for_green = True
        self.classic_ready_to_click = False
        self.classic_start_time = None

        self.classic_click_area.config(text="Warten...", bg="#cc3333", activebackground="#cc3333")
        self.classic_info_label.config(text="Nicht klicken, bis das Feld grün wird.")

        self.classic_timer_id = self.root.after(delay_ms, self.turn_classic_green)

    def turn_classic_green(self):
        self.classic_waiting_for_green = False
        self.classic_ready_to_click = True
        self.classic_start_time = time.perf_counter()

        self.classic_click_area.config(text="JETZT KLICKEN!", bg="#22aa44", activebackground="#22aa44")
        self.classic_info_label.config(text="Klick!")

    def classic_too_early(self):
        if self.classic_timer_id is not None:
            self.root.after_cancel(self.classic_timer_id)
            self.classic_timer_id = None

        self.classic_waiting_for_green = False
        self.classic_ready_to_click = False
        self.classic_start_time = None

        self.classic_click_area.config(text="Zu früh! Nochmal starten", bg="#ffcc33", activebackground="#ffcc33")
        self.classic_info_label.config(text="Zu früh geklickt. Drücke erneut zum Neustart.")

    def record_classic_reaction(self):
        reaction_ms = round((time.perf_counter() - self.classic_start_time) * 1000, 1)
        timestamp = datetime.now()

        record = {
            "timestamp": timestamp,
            "mode": "classic",
            "reaction_ms": reaction_ms,
            "attempts_to_hit": None,
            "mean_miss_px": None,
            "last_miss_px": None,
            "hit_offset_px": None,
            "target_x_px": None,
            "target_y_px": None,
            "canvas_width_px": None,
            "canvas_height_px": None,
            "hit_radius_px": None,
        }

        self.add_record(record)

        self.classic_waiting_for_green = False
        self.classic_ready_to_click = False
        self.classic_start_time = None

        self.classic_click_area.config(
            text=f"{reaction_ms:.1f} ms\nNochmal starten",
            bg="#dddddd",
            activebackground="#dddddd"
        )
        self.classic_info_label.config(text="Messung gespeichert. Drücke erneut für den nächsten Versuch.")

    # ---------- Zielkreis-Modus ----------

    def start_target_trial(self):
        if self.target_waiting or self.target_active:
            return

        delay_ms = random.randint(1500, 5000)

        self.target_waiting = True
        self.target_active = False
        self.target_start_time = None
        self.target_attempts = 0
        self.target_miss_distances = []
        self.target_center = None

        self.target_start_button.config(state="disabled")
        self.target_canvas.config(bg="#cc3333")
        self.draw_canvas_message("Warten... noch nicht klicken.")
        self.target_info_label.config(text="Nicht klicken, bis der Zielkreis erscheint.")

        self.target_timer_id = self.root.after(delay_ms, self.show_random_target)

    def show_random_target(self):
        self.target_waiting = False
        self.target_active = True
        self.target_start_time = time.perf_counter()

        self.target_canvas.update_idletasks()
        width = max(self.target_canvas.winfo_width(), 500)
        height = max(self.target_canvas.winfo_height(), 240)
        margin = self.target_radius + 10

        x = random.randint(margin, max(margin, width - margin))
        y = random.randint(margin, max(margin, height - margin))
        self.target_center = (x, y)

        self.target_canvas.delete("all")
        self.target_canvas.config(bg="#eeeeee")
        self.target_canvas.create_oval(
            x - self.target_radius,
            y - self.target_radius,
            x + self.target_radius,
            y + self.target_radius,
            fill="#111111",
            outline="#111111"
        )

        self.target_info_label.config(text="Zielkreis treffen. Jeder Fehlklick zählt als zusätzlicher Versuch.")

    def handle_target_canvas_click(self, event):
        if self.target_waiting:
            self.target_too_early()
            return

        if not self.target_active or self.target_center is None:
            return

        self.target_attempts += 1

        x0, y0 = self.target_center
        center_distance = math.hypot(event.x - x0, event.y - y0)
        edge_miss = max(0.0, center_distance - self.target_radius)

        if center_distance <= self.target_radius:
            self.record_target_reaction(center_distance)
        else:
            self.target_miss_distances.append(edge_miss)
            self.draw_miss_marker(event.x, event.y)
            self.target_info_label.config(
                text=(
                    f"Daneben: {edge_miss:.1f} px außerhalb des Kreisrands. "
                    f"Versuch {self.target_attempts}. Weiter auf denselben Kreis klicken."
                )
            )

    def draw_miss_marker(self, x, y):
        size = 5
        self.target_canvas.create_line(x - size, y - size, x + size, y + size, width=2)
        self.target_canvas.create_line(x - size, y + size, x + size, y - size, width=2)

    def record_target_reaction(self, hit_offset_px):
        reaction_ms = round((time.perf_counter() - self.target_start_time) * 1000, 1)
        timestamp = datetime.now()

        mean_miss = round(statistics.mean(self.target_miss_distances), 1) if self.target_miss_distances else 0.0
        last_miss = round(self.target_miss_distances[-1], 1) if self.target_miss_distances else 0.0

        canvas_width = self.target_canvas.winfo_width()
        canvas_height = self.target_canvas.winfo_height()
        target_x, target_y = self.target_center

        record = {
            "timestamp": timestamp,
            "mode": "target",
            "reaction_ms": reaction_ms,
            "attempts_to_hit": self.target_attempts,
            "mean_miss_px": mean_miss,
            "last_miss_px": last_miss,
            "hit_offset_px": round(hit_offset_px, 1),
            "target_x_px": target_x,
            "target_y_px": target_y,
            "canvas_width_px": canvas_width,
            "canvas_height_px": canvas_height,
            "hit_radius_px": self.target_radius,
        }

        self.add_record(record)

        self.target_active = False
        self.target_waiting = False
        self.target_start_time = None
        self.target_start_button.config(state="normal")

        self.target_canvas.config(bg="#dddddd")
        self.draw_canvas_message(
            f"Treffer: {reaction_ms:.1f} ms | "
            f"Versuche: {self.target_attempts} | "
            f"mittlere Abweichung: {mean_miss:.1f} px"
        )
        self.target_info_label.config(text="Messung gespeichert. Starte den nächsten Zielversuch.")

    def target_too_early(self):
        if self.target_timer_id is not None:
            self.root.after_cancel(self.target_timer_id)
            self.target_timer_id = None

        self.target_waiting = False
        self.target_active = False
        self.target_start_time = None
        self.target_center = None
        self.target_start_button.config(state="normal")

        self.target_canvas.config(bg="#ffcc33")
        self.draw_canvas_message("Zu früh geklickt. Erneut starten.")
        self.target_info_label.config(text="Zu früh geklickt. Drücke erneut auf Zielversuch starten.")

    def cancel_target_trial(self):
        if self.target_timer_id is not None:
            self.root.after_cancel(self.target_timer_id)
            self.target_timer_id = None

        self.target_waiting = False
        self.target_active = False
        self.target_start_time = None
        self.target_center = None
        self.target_attempts = 0
        self.target_miss_distances = []
        self.target_start_button.config(state="normal")

        self.target_canvas.config(bg="#dddddd")
        self.draw_canvas_message("Zielversuch abgebrochen.")
        self.target_info_label.config(text="Start drücken. Nach kurzer Wartezeit erscheint ein Zielkreis.")

    def draw_canvas_message(self, text):
        self.target_canvas.update_idletasks()
        width = max(self.target_canvas.winfo_width(), 500)
        height = max(self.target_canvas.winfo_height(), 240)

        self.target_canvas.delete("all")
        self.target_canvas.create_text(
            width / 2,
            height / 2,
            text=text,
            font=("Arial", 18, "bold"),
            width=max(300, width - 80),
            justify="center"
        )

    # ---------- Daten ----------

    def add_record(self, record):
        self.records.append(record)
        self.records.sort(key=lambda r: r["timestamp"])
        self.save_record(record)
        self.refresh_analysis()

    def load_results(self):
        loaded_from_new_file = False

        if self.data_file.exists():
            self.records.extend(self.read_records_from_csv(self.data_file, default_mode=None))
            loaded_from_new_file = True

        if not loaded_from_new_file and self.legacy_file.exists():
            self.records.extend(self.read_records_from_csv(self.legacy_file, default_mode="classic"))
            self.records.sort(key=lambda r: r["timestamp"])
            self.write_all_records_to_data_file()

    def read_records_from_csv(self, file_path, default_mode=None):
        records = []

        try:
            with file_path.open("r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)

                for row in reader:
                    reaction_ms = self.parse_float(row.get("reaction_ms"))
                    if reaction_ms is None:
                        continue

                    timestamp = self.parse_timestamp(row.get("timestamp"))
                    mode = row.get("mode") or default_mode or "classic"

                    record = {
                        "timestamp": timestamp,
                        "mode": mode,
                        "reaction_ms": reaction_ms,
                        "attempts_to_hit": self.parse_int(row.get("attempts_to_hit")),
                        "mean_miss_px": self.parse_float(row.get("mean_miss_px")),
                        "last_miss_px": self.parse_float(row.get("last_miss_px")),
                        "hit_offset_px": self.parse_float(row.get("hit_offset_px")),
                        "target_x_px": self.parse_float(row.get("target_x_px")),
                        "target_y_px": self.parse_float(row.get("target_y_px")),
                        "canvas_width_px": self.parse_float(row.get("canvas_width_px")),
                        "canvas_height_px": self.parse_float(row.get("canvas_height_px")),
                        "hit_radius_px": self.parse_float(row.get("hit_radius_px")),
                    }

                    records.append(record)

        except Exception:
            messagebox.showwarning("Warnung", f"Die CSV konnte nicht vollständig gelesen werden:\n{file_path}")

        return records

    @staticmethod
    def parse_timestamp(value):
        if not value:
            return datetime.now()

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now()

    @staticmethod
    def parse_float(value):
        if value in (None, ""):
            return None

        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def parse_int(value):
        if value in (None, ""):
            return None

        try:
            return int(float(value))
        except ValueError:
            return None

    def csv_ready_record(self, record):
        output = {}

        for field in self.FIELDNAMES:
            value = record.get(field)

            if field == "timestamp" and isinstance(value, datetime):
                output[field] = value.isoformat(timespec="seconds")
            elif value is None:
                output[field] = ""
            else:
                output[field] = value

        return output

    def save_record(self, record):
        file_exists = self.data_file.exists() and self.data_file.stat().st_size > 0

        with self.data_file.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            writer.writerow(self.csv_ready_record(record))

    def write_all_records_to_data_file(self):
        with self.data_file.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()

            for record in sorted(self.records, key=lambda r: r["timestamp"]):
                writer.writerow(self.csv_ready_record(record))

    # ---------- Auswertung ----------

    def get_selected_metric_spec(self):
        return self.metric_specs[self.graph_metric_var.get()]

    def get_metric_records(self):
        spec = self.get_selected_metric_spec()
        mode = spec["mode"]
        field = spec["field"]

        metric_records = []

        for record in sorted(self.records, key=lambda r: r["timestamp"]):
            if record.get("mode") != mode:
                continue

            value = record.get(field)
            if value is None:
                continue

            metric_records.append({
                "timestamp": record["timestamp"],
                "value": float(value),
                "record": record,
            })

        return metric_records

    def get_sessions(self, metric_records):
        if not metric_records:
            return []

        sessions = []
        current_session = [metric_records[0]]

        for previous, current in zip(metric_records, metric_records[1:]):
            gap = (current["timestamp"] - previous["timestamp"]).total_seconds()

            if gap > self.SESSION_GAP_SECONDS:
                sessions.append(current_session)
                current_session = [current]
            else:
                current_session.append(current)

        sessions.append(current_session)
        return sessions

    def rolling_average(self, values):
        rolling = []

        for i in range(len(values)):
            start = max(0, i - self.ROLLING_WINDOW + 1)
            window = values[start:i + 1]
            rolling.append(statistics.mean(window))

        return rolling

    def update_stats(self):
        spec = self.get_selected_metric_spec()
        metric_records = self.get_metric_records()
        values = [r["value"] for r in metric_records]
        unit = spec["unit"]

        n = len(values)
        self.count_label.config(text=f"Messungen: {n}")

        if n == 0:
            self.mean_label.config(text="Gesamt-Mittelwert: –")
            self.std_label.config(text="Gesamt-s: –")
            self.session_label.config(text="Aktuelle Session: –")
            self.session_mean_label.config(text="Session-Mittelwert: –")
            self.session_std_label.config(text="Session-s: –")
            return

        total_mean = statistics.mean(values)
        self.mean_label.config(text=f"Gesamt-Mittelwert: {total_mean:.1f} {unit}")

        if n >= 2:
            total_std = statistics.stdev(values)
            self.std_label.config(text=f"Gesamt-s: {total_std:.1f} {unit}")
        else:
            self.std_label.config(text="Gesamt-s: –")

        sessions = self.get_sessions(metric_records)
        current_session = sessions[-1]
        session_values = [r["value"] for r in current_session]

        session_start = current_session[0]["timestamp"].strftime("%d.%m. %H:%M")
        session_end = current_session[-1]["timestamp"].strftime("%H:%M")

        self.session_label.config(text=f"Aktuelle Session: {len(session_values)} Werte, {session_start}–{session_end}")

        session_mean = statistics.mean(session_values)
        self.session_mean_label.config(text=f"Session-Mittelwert: {session_mean:.1f} {unit}")

        if len(session_values) >= 2:
            session_std = statistics.stdev(session_values)
            self.session_std_label.config(text=f"Session-s: {session_std:.1f} {unit}")
        else:
            self.session_std_label.config(text="Session-s: –")

    def update_graph(self):
        self.ax.clear()

        spec = self.get_selected_metric_spec()
        metric_records = self.get_metric_records()
        values = [r["value"] for r in metric_records]
        unit = spec["unit"]

        if not values:
            self.ax.text(
                0.5, 0.5,
                "Noch keine Messungen für diese Auswahl",
                ha="center",
                va="center",
                transform=self.ax.transAxes
            )
            self.format_graph(spec, unit)
            return

        x = list(range(1, len(values) + 1))

        self.ax.plot(x, values, marker="o", label="Einzelmessung")

        if len(values) >= 2:
            rolling = self.rolling_average(values)
            self.ax.plot(x, rolling, linewidth=2, label=f"Gleitender Mittelwert ({self.ROLLING_WINDOW} Werte)")

        total_mean = statistics.mean(values)
        self.ax.axhline(total_mean, linestyle="--", label=f"Gesamt-Mittelwert: {total_mean:.1f} {unit}")

        sessions = self.get_sessions(metric_records)
        index_offset = 0
        session_mean_label_used = False
        session_std_label_used = False

        for session_number, session in enumerate(sessions, start=1):
            session_values = [r["value"] for r in session]
            session_mean = statistics.mean(session_values)
            x_start = index_offset + 1
            x_end = index_offset + len(session_values)

            mean_label = "Session-Mittelwert" if not session_mean_label_used else None
            self.ax.hlines(session_mean, x_start, x_end, linestyles=":", linewidth=3, label=mean_label)
            session_mean_label_used = True

            if len(session_values) >= 2:
                session_std = statistics.stdev(session_values)
                std_label = "Session ± s" if not session_std_label_used else None
                self.ax.fill_between(
                    [x_start, x_end],
                    [session_mean - session_std, session_mean - session_std],
                    [session_mean + session_std, session_mean + session_std],
                    alpha=0.15,
                    label=std_label
                )
                session_std_label_used = True

            if session_number < len(sessions):
                self.ax.axvline(x_end + 0.5, linestyle=":", alpha=0.4)

            index_offset += len(session_values)

        ymin = min(values)
        ymax = max(values)

        for session in sessions:
            session_values = [r["value"] for r in session]
            if len(session_values) >= 2:
                session_mean = statistics.mean(session_values)
                session_std = statistics.stdev(session_values)
                ymin = min(ymin, session_mean - session_std)
                ymax = max(ymax, session_mean + session_std)

        padding = max((ymax - ymin) * 0.12, 1.0)
        self.ax.set_xlim(1, max(2, len(values)))
        self.ax.set_ylim(max(0, ymin - padding), ymax + padding)

        self.ax.legend(loc="best", fontsize=9)
        self.format_graph(spec, unit)

    def format_graph(self, spec, unit):
        self.ax.set_title(spec["title"], fontsize=13)
        self.ax.set_xlabel("Versuch")
        self.ax.set_ylabel(unit)
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()

    # ---------- Buttons ----------

    def reset_results(self):
        answer = messagebox.askyesno(
            "Bestätigen",
            "Wirklich alle Ergebnisse dieser Multimode-Datei löschen?\n"
            "Die alte reaction_results.csv bleibt unangetastet."
        )

        if not answer:
            return

        self.records.clear()
        self.write_all_records_to_data_file()
        self.refresh_analysis()

        self.classic_click_area.config(text="Start", bg="#dddddd", activebackground="#dddddd")
        self.classic_info_label.config(text="Start drücken. Wenn das Feld grün wird, sofort klicken.")

        self.target_canvas.config(bg="#dddddd")
        self.draw_canvas_message("Start drücken, dann Zielkreis treffen.")
        self.target_info_label.config(text="Start drücken. Nach kurzer Wartezeit erscheint ein Zielkreis.")

    def export_csv(self):
        if not self.records:
            messagebox.showinfo("Keine Daten", "Es gibt noch keine gespeicherten Messungen.")
            return

        target = filedialog.asksaveasfilename(
            title="CSV exportieren",
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv")]
        )

        if not target:
            return

        with Path(target).open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()

            for record in sorted(self.records, key=lambda r: r["timestamp"]):
                writer.writerow(self.csv_ready_record(record))

        messagebox.showinfo("Export fertig", f"CSV exportiert nach:\n{target}")

    def show_analysis_info(self):
        messagebox.showinfo(
            "Auswertung",
            "Sessions:\n"
            "Eine neue Session beginnt automatisch, wenn zwischen zwei Messungen "
            "mehr als 1 Stunde liegt.\n\n"
            "Gleitender Mittelwert:\n"
            f"Berechnet über die letzten {self.ROLLING_WINDOW} Werte der aktuell ausgewählten Graph-Größe.\n\n"
            "Zielkreis-Modus:\n"
            "• Reaktionszeit: Zeit vom Erscheinen des Kreises bis zum Treffer\n"
            "• Versuche bis Treffer: Anzahl aller Klicks bis zum Treffer\n"
            "• mittlere Abweichung: Mittelwert aller Fehlklick-Abstände außerhalb des Kreisrands\n"
            "• letzter Fehlklick: Abstand des letzten Fehlklicks außerhalb des Kreisrands\n"
            "• Treffer-Abstand: Abstand des erfolgreichen Klicks vom Kreismittelpunkt\n\n"
            "Graph:\n"
            "• Punkte/Linie: Einzelmessungen\n"
            "• Zusatzlinie: gleitender Mittelwert\n"
            "• gestrichelte Horizontale: Gesamt-Mittelwert\n"
            "• gepunktete Abschnitte: Session-Mittelwerte\n"
            "• transparentes Band: Session-Mittelwert ± Standardabweichung"
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = ReactionTestApp(root)
    root.mainloop()
