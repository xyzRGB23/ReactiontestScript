import csv
import random
import statistics
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class ReactionTestApp:
    SESSION_GAP_SECONDS = 60 * 60      # Neue Session nach > 1 h Abstand
    ROLLING_WINDOW = 5                 # Gleitender Durchschnitt über die letzten 5 Versuche

    def __init__(self, root):
        self.root = root
        self.root.title("Reaktionsgeschwindigkeitstest")
        self.root.geometry("1000x720")
        self.root.minsize(850, 600)

        self.data_file = Path(__file__).with_name("reaction_results.csv")

        # Jeder Eintrag: {"timestamp": datetime, "reaction_ms": float}
        self.records = []

        self.waiting_for_green = False
        self.ready_to_click = False
        self.start_time = None
        self.timer_id = None

        self.load_results()
        self.build_gui()
        self.update_stats()
        self.update_graph()

    def build_gui(self):
        self.title_label = tk.Label(
            self.root,
            text="Reaktionsgeschwindigkeitstest",
            font=("Arial", 22, "bold")
        )
        self.title_label.pack(pady=10)

        self.info_label = tk.Label(
            self.root,
            text="Drücke Start. Sobald das Feld grün wird, so schnell wie möglich klicken.",
            font=("Arial", 12)
        )
        self.info_label.pack(pady=5)

        self.click_area = tk.Button(
            self.root,
            text="Start",
            font=("Arial", 28, "bold"),
            bg="#dddddd",
            activebackground="#dddddd",
            height=3,
            command=self.handle_click
        )
        self.click_area.pack(fill="x", padx=25, pady=15)

        stats_frame = tk.Frame(self.root)
        stats_frame.pack(pady=5)

        self.count_label = tk.Label(stats_frame, text="Messungen: 0", font=("Arial", 12))
        self.count_label.grid(row=0, column=0, padx=12, pady=3)

        self.mean_label = tk.Label(stats_frame, text="Gesamt-Mittelwert: –", font=("Arial", 12))
        self.mean_label.grid(row=0, column=1, padx=12, pady=3)

        self.std_label = tk.Label(stats_frame, text="Gesamt-s: –", font=("Arial", 12))
        self.std_label.grid(row=0, column=2, padx=12, pady=3)

        self.session_label = tk.Label(stats_frame, text="Aktuelle Session: –", font=("Arial", 12))
        self.session_label.grid(row=1, column=0, padx=12, pady=3)

        self.session_mean_label = tk.Label(stats_frame, text="Session-Mittelwert: –", font=("Arial", 12))
        self.session_mean_label.grid(row=1, column=1, padx=12, pady=3)

        self.session_std_label = tk.Label(stats_frame, text="Session-s: –", font=("Arial", 12))
        self.session_std_label.grid(row=1, column=2, padx=12, pady=3)

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5)

        self.reset_button = tk.Button(button_frame, text="Alle Ergebnisse löschen", command=self.reset_results)
        self.reset_button.grid(row=0, column=0, padx=8)

        self.export_button = tk.Button(button_frame, text="CSV exportieren", command=self.export_csv)
        self.export_button.grid(row=0, column=1, padx=8)

        self.session_info_button = tk.Button(
            button_frame,
            text="Session-Regel anzeigen",
            command=self.show_session_rule
        )
        self.session_info_button.grid(row=0, column=2, padx=8)

        self.fig = Figure(figsize=(9, 4.8), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=25, pady=15)

    def handle_click(self):
        if not self.waiting_for_green and not self.ready_to_click:
            self.start_trial()
        elif self.waiting_for_green:
            self.too_early()
        elif self.ready_to_click:
            self.record_reaction()

    def start_trial(self):
        delay_ms = random.randint(1500, 5000)

        self.waiting_for_green = True
        self.ready_to_click = False
        self.start_time = None

        self.click_area.config(
            text="Warten...",
            bg="#cc3333",
            activebackground="#cc3333"
        )
        self.info_label.config(text="Nicht klicken, bis das Feld grün wird.")

        self.timer_id = self.root.after(delay_ms, self.turn_green)

    def turn_green(self):
        self.waiting_for_green = False
        self.ready_to_click = True
        self.start_time = time.perf_counter()

        self.click_area.config(
            text="JETZT KLICKEN!",
            bg="#22aa44",
            activebackground="#22aa44"
        )
        self.info_label.config(text="Klick!")

    def too_early(self):
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

        self.waiting_for_green = False
        self.ready_to_click = False
        self.start_time = None

        self.click_area.config(
            text="Zu früh! Nochmal starten",
            bg="#ffcc33",
            activebackground="#ffcc33"
        )
        self.info_label.config(text="Zu früh geklickt. Drücke erneut zum Neustart.")

    def record_reaction(self):
        reaction_ms = (time.perf_counter() - self.start_time) * 1000
        reaction_ms = round(reaction_ms, 1)
        timestamp = datetime.now()

        self.records.append({
            "timestamp": timestamp,
            "reaction_ms": reaction_ms
        })

        self.save_result(timestamp, reaction_ms)

        self.waiting_for_green = False
        self.ready_to_click = False
        self.start_time = None

        self.click_area.config(
            text=f"{reaction_ms:.1f} ms\nNochmal starten",
            bg="#dddddd",
            activebackground="#dddddd"
        )
        self.info_label.config(text="Messung gespeichert. Drücke erneut für den nächsten Versuch.")

        self.update_stats()
        self.update_graph()

    def load_results(self):
        if not self.data_file.exists():
            return

        try:
            with self.data_file.open("r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)

                for row in reader:
                    reaction_ms = float(row["reaction_ms"])

                    raw_timestamp = row.get("timestamp", "")
                    try:
                        timestamp = datetime.fromisoformat(raw_timestamp)
                    except ValueError:
                        # Fallback für beschädigte/alte Zeitstempel
                        timestamp = datetime.now()

                    self.records.append({
                        "timestamp": timestamp,
                        "reaction_ms": reaction_ms
                    })

            self.records.sort(key=lambda r: r["timestamp"])

        except Exception:
            messagebox.showwarning(
                "Warnung",
                "Die gespeicherte CSV konnte nicht vollständig gelesen werden."
            )

    def save_result(self, timestamp, reaction_ms):
        file_exists = self.data_file.exists()

        with self.data_file.open("a", newline="", encoding="utf-8") as file:
            fieldnames = ["timestamp", "reaction_ms"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "reaction_ms": reaction_ms
            })

    def get_values(self):
        return [record["reaction_ms"] for record in self.records]

    def get_sessions(self):
        if not self.records:
            return []

        sorted_records = sorted(self.records, key=lambda r: r["timestamp"])
        sessions = []
        current_session = [sorted_records[0]]

        for previous, current in zip(sorted_records, sorted_records[1:]):
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
        values = self.get_values()
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
        self.mean_label.config(text=f"Gesamt-Mittelwert: {total_mean:.1f} ms")

        if n >= 2:
            total_std = statistics.stdev(values)
            self.std_label.config(text=f"Gesamt-s: {total_std:.1f} ms")
        else:
            self.std_label.config(text="Gesamt-s: –")

        sessions = self.get_sessions()
        current_session = sessions[-1]
        session_values = [record["reaction_ms"] for record in current_session]

        session_start = current_session[0]["timestamp"].strftime("%d.%m. %H:%M")
        session_end = current_session[-1]["timestamp"].strftime("%H:%M")

        self.session_label.config(
            text=f"Aktuelle Session: {len(session_values)} Werte, {session_start}–{session_end}"
        )

        session_mean = statistics.mean(session_values)
        self.session_mean_label.config(text=f"Session-Mittelwert: {session_mean:.1f} ms")

        if len(session_values) >= 2:
            session_std = statistics.stdev(session_values)
            self.session_std_label.config(text=f"Session-s: {session_std:.1f} ms")
        else:
            self.session_std_label.config(text="Session-s: –")

    def update_graph(self):
        self.ax.clear()

        if not self.records:
            self.ax.text(
                0.5, 0.5,
                "Noch keine Messungen",
                ha="center",
                va="center",
                transform=self.ax.transAxes
            )
            self.format_graph()
            return

        sorted_records = sorted(self.records, key=lambda r: r["timestamp"])
        values = [record["reaction_ms"] for record in sorted_records]
        x = list(range(1, len(values) + 1))

        self.ax.plot(x, values, marker="o", label="Einzelmessung")

        rolling = self.rolling_average(values)
        if len(rolling) >= 2:
            self.ax.plot(
                x,
                rolling,
                linewidth=2,
                label=f"Gleitender Mittelwert ({self.ROLLING_WINDOW} Werte)"
            )

        total_mean = statistics.mean(values)
        self.ax.axhline(
            total_mean,
            linestyle="--",
            label=f"Gesamt-Mittelwert: {total_mean:.1f} ms"
        )

        sessions = self.get_sessions()
        index_offset = 0
        session_mean_label_used = False
        session_std_label_used = False

        for session_number, session in enumerate(sessions, start=1):
            session_values = [record["reaction_ms"] for record in session]
            session_mean = statistics.mean(session_values)
            x_start = index_offset + 1
            x_end = index_offset + len(session_values)

            mean_label = "Session-Mittelwert" if not session_mean_label_used else None
            self.ax.hlines(
                session_mean,
                x_start,
                x_end,
                linestyles=":",
                linewidth=3,
                label=mean_label
            )
            session_mean_label_used = True

            # Session-s als Band: Mittelwert ± Standardabweichung
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

            # Dezente vertikale Trennung zwischen Sessions
            if session_number < len(sessions):
                self.ax.axvline(x_end + 0.5, linestyle=":", alpha=0.4)

            index_offset += len(session_values)

        self.ax.set_xlim(1, max(2, len(values)))

        ymin = max(0, min(values) - 50)
        ymax = max(values) + 50

        # Bei s-Bändern den sichtbaren Bereich erweitern
        for session in sessions:
            session_values = [record["reaction_ms"] for record in session]
            if len(session_values) >= 2:
                session_mean = statistics.mean(session_values)
                session_std = statistics.stdev(session_values)
                ymin = min(ymin, max(0, session_mean - session_std - 20))
                ymax = max(ymax, session_mean + session_std + 20)

        self.ax.set_ylim(ymin, ymax)
        self.ax.legend(loc="best")
        self.format_graph()

    def format_graph(self):
        self.ax.set_title("Reaktionszeit, Session-Mittelwerte und gleitender Durchschnitt")
        self.ax.set_xlabel("Versuch")
        self.ax.set_ylabel("Reaktionszeit [ms]")
        self.ax.grid(True, alpha=0.3)

        self.fig.tight_layout()
        self.canvas.draw()

    def reset_results(self):
        answer = messagebox.askyesno(
            "Bestätigen",
            "Wirklich alle gespeicherten Ergebnisse löschen?"
        )
        if not answer:
            return

        self.records.clear()

        if self.data_file.exists():
            self.data_file.unlink()

        self.update_stats()
        self.update_graph()

        self.click_area.config(
            text="Start",
            bg="#dddddd",
            activebackground="#dddddd"
        )
        self.info_label.config(
            text="Drücke Start. Sobald das Feld grün wird, so schnell wie möglich klicken."
        )

    def export_csv(self):
        if not self.data_file.exists():
            messagebox.showinfo("Keine Daten", "Es gibt noch keine gespeicherten Messungen.")
            return

        target = filedialog.asksaveasfilename(
            title="CSV exportieren",
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv")]
        )

        if not target:
            return

        Path(target).write_bytes(self.data_file.read_bytes())
        messagebox.showinfo("Export fertig", f"CSV exportiert nach:\n{target}")

    def show_session_rule(self):
        messagebox.showinfo(
            "Session-Auswertung",
            "Eine neue Session beginnt automatisch, wenn zwischen zwei Messungen "
            "mehr als 1 Stunde liegt.\n\n"
            f"Der gleitende Durchschnitt wird über die letzten {self.ROLLING_WINDOW} "
            "Messungen berechnet.\n\n"
            "Im Graphen bedeutet:\n"
            "• Punkte/Linie: Einzelmessungen\n"
            "• Durchgezogene Zusatzlinie: gleitender Mittelwert\n"
            "• Gestrichelte horizontale Linie: Gesamt-Mittelwert\n"
            "• Gepunktete horizontale Abschnitte: Session-Mittelwerte\n"
            "• Transparentes Band: Session-Mittelwert ± Standardabweichung"
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = ReactionTestApp(root)
    root.mainloop()
