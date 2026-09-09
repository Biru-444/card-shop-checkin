"""Card shop check-in and reporting app, built with Flet and SQLite."""

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import flet as ft


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "card_shop.db"
DEFAULT_GAMES = ["Card A", "Card B", "Card C"]


class Store:
    def __init__(self, db_path: Path):
        self.connection = sqlite3.connect(db_path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                phone TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visit_games (
                visit_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                PRIMARY KEY (visit_id, game_name),
                FOREIGN KEY (visit_id) REFERENCES visits(id) ON DELETE CASCADE
            );
            """
        )
        self.connection.commit()

    def add_visit(self, name: str, phone: str, games: list[str]):
        now = datetime.now().isoformat(timespec="seconds")
        cursor = self.connection.execute(
            "INSERT INTO visits (customer_name, phone, created_at) VALUES (?, ?, ?)",
            (name.strip(), phone.strip(), now),
        )
        self.connection.executemany(
            "INSERT INTO visit_games (visit_id, game_name) VALUES (?, ?)",
            [(cursor.lastrowid, game) for game in games],
        )
        self.connection.commit()

    def summary_for_day(self, date_text: str):
        total = self.connection.execute(
            "SELECT COUNT(*) FROM visits WHERE date(created_at) = ?", (date_text,)
        ).fetchone()[0]
        games = self.connection.execute(
            """
            SELECT vg.game_name, COUNT(*) AS players
            FROM visit_games vg JOIN visits v ON v.id = vg.visit_id
            WHERE date(v.created_at) = ?
            GROUP BY vg.game_name ORDER BY players DESC, vg.game_name
            """,
            (date_text,),
        ).fetchall()
        return total, games

    def summary_for_month(self, month_text: str):
        games = self.connection.execute(
            """
            SELECT vg.game_name, COUNT(*) AS players
            FROM visit_games vg JOIN visits v ON v.id = vg.visit_id
            WHERE strftime('%Y-%m', v.created_at) = ?
            GROUP BY vg.game_name ORDER BY players DESC, vg.game_name
            """,
            (month_text,),
        ).fetchall()
        days = self.connection.execute(
            """
            SELECT date(created_at) AS day, COUNT(*) AS visitors
            FROM visits WHERE strftime('%Y-%m', created_at) = ?
            GROUP BY day ORDER BY day
            """,
            (month_text,),
        ).fetchall()
        return games, days


def main(page: ft.Page):
    store = Store(DB_PATH)
    page.title = "Card Shop Check-in"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F7F8FC"

    name_field = ft.TextField(label="ชื่อเล่น", value="", autofocus=True, expand=True)
    phone_field = ft.TextField(label="เบอร์โทร", value="", keyboard_type=ft.KeyboardType.PHONE, expand=True)
    selected_games: set[str] = set()
    game_checks: list[ft.Checkbox] = []
    body = ft.Container(expand=True, padding=24)

    def notify(message: str, error: bool = False):
        page.snack_bar = ft.SnackBar(ft.Text(message), bgcolor="#B42318" if error else "#16794B")
        page.snack_bar.open = True
        page.update()

    def game_rows(rows, empty_message):
        if not rows:
            return ft.Text(empty_message, color="#667085")
        maximum = max(row[1] for row in rows) or 1
        result = []
        for game, count in rows:
            result.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row([ft.Text(game, weight=ft.FontWeight.W_600), ft.Text(f"{count} คน")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.ProgressBar(value=count / maximum, color="#635BFF", bgcolor="#E7E5FF"),
                        ],
                        spacing=6,
                    ),
                    padding=ft.Padding(bottom=14),
                )
            )
        return ft.Column(result, spacing=2)

    def check_in(e):
        name = (name_field.value or "").strip()
        phone = (phone_field.value or "").strip()
        if not name and not phone:
            notify("กรอกชื่อเล่นหรือเบอร์โทรอย่างน้อย 1 รายการ", True)
            return
        if not selected_games:
            notify("เลือกเกมที่ต้องการเล่นอย่างน้อย 1 เกม", True)
            return
        store.add_visit(name, phone, sorted(selected_games))
        name_field.value = ""
        phone_field.value = ""
        selected_games.clear()
        for control in game_checks:
            control.value = False
        page.update()
        notify("ลงทะเบียนเรียบร้อย ยินดีต้อนรับครับ")

    def checkin_view():
        game_checks.clear()
        for game in DEFAULT_GAMES:
            def choose(e, game_name=game):
                if e.control.value:
                    selected_games.add(game_name)
                else:
                    selected_games.discard(game_name)
            checkbox = ft.Checkbox(label=game, value=False, on_change=choose)
            game_checks.append(checkbox)
        return ft.Column(
            [
                ft.Text("ลงทะเบียนก่อนเล่น", size=28, weight=ft.FontWeight.BOLD),
                ft.Text("กรอกชื่อเล่นหรือเบอร์โทร แล้วเลือกเกมที่ต้องการเล่น", color="#667085"),
                ft.Container(height=12),
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text("ข้อมูลผู้เล่น", size=18, weight=ft.FontWeight.W_600),
                                ft.Row([name_field, phone_field], wrap=True),
                                ft.Divider(),
                                ft.Text("เกมที่ต้องการเล่น (เลือกได้มากกว่า 1 เกม)", weight=ft.FontWeight.W_600),
                                ft.Column(game_checks),
                                ft.Container(height=8),
                                ft.FilledButton("ยืนยันการลงทะเบียน", icon=ft.Icons.CHECK_CIRCLE, on_click=check_in, height=48),
                            ],
                            spacing=14,
                        ),
                        padding=24,
                    )
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    def daily_view():
        today = datetime.now().date().isoformat()
        total, games = store.summary_for_day(today)
        return ft.Column(
            [
                ft.Text("สรุปวันนี้", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(datetime.now().strftime("%d/%m/%Y"), color="#667085"),
                ft.Container(
                    content=ft.Column([ft.Text("ผู้เข้าใช้ร้าน", color="#667085"), ft.Text(f"{total} คน", size=36, weight=ft.FontWeight.BOLD)]),
                    bgcolor="#E9E7FF", border_radius=14, padding=20, width=220,
                ),
                ft.Card(content=ft.Container(content=ft.Column([ft.Text("ผู้เล่นแยกตามเกม", size=18, weight=ft.FontWeight.W_600), game_rows(games, "วันนี้ยังไม่มีข้อมูล")]), padding=20)),
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )

    def monthly_view():
        month = datetime.now().strftime("%Y-%m")
        games, days = store.summary_for_month(month)
        busiest = max(days, key=lambda item: item[1]) if days else None
        trend = ft.Column([
            ft.Row([ft.Text(day[8:] + "/" + day[5:7]), ft.ProgressBar(value=count / max(1, max(item[1] for item in days)), expand=True, color="#12B76A"), ft.Text(f"{count} คน", width=52)], spacing=10)
            for day, count in days
        ], spacing=10) if days else ft.Text("เดือนนี้ยังไม่มีข้อมูล", color="#667085")
        return ft.Column(
            [
                ft.Text("สรุปรายเดือน", size=28, weight=ft.FontWeight.BOLD),
                ft.Text(datetime.now().strftime("เดือน %m/%Y"), color="#667085"),
                ft.Row([
                    ft.Container(content=ft.Column([ft.Text("วันที่คนเยอะที่สุด", color="#667085"), ft.Text(f"{busiest[0][8:]}/{busiest[0][5:7]} · {busiest[1]} คน" if busiest else "—", size=20, weight=ft.FontWeight.BOLD)]), bgcolor="#D1FADF", border_radius=14, padding=18),
                ]),
                ft.Card(content=ft.Container(content=ft.Column([ft.Text("ยอดผู้เล่นสะสมรายเกม", size=18, weight=ft.FontWeight.W_600), game_rows(games, "เดือนนี้ยังไม่มีข้อมูล")]), padding=20)),
                ft.Card(content=ft.Container(content=ft.Column([ft.Text("แนวโน้มผู้เข้าใช้รายวัน", size=18, weight=ft.FontWeight.W_600), trend]), padding=20)),
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
        )

    views = [checkin_view, daily_view, monthly_view]

    def change_tab(e):
        body.content = views[e.control.selected_index]()
        page.update()

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=change_tab,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.APP_REGISTRATION_OUTLINED, selected_icon=ft.Icons.APP_REGISTRATION, label="ลงทะเบียน"),
            ft.NavigationBarDestination(icon=ft.Icons.TODAY_OUTLINED, selected_icon=ft.Icons.TODAY, label="วันนี้"),
            ft.NavigationBarDestination(icon=ft.Icons.INSIGHTS_OUTLINED, selected_icon=ft.Icons.INSIGHTS, label="รายเดือน"),
        ],
    )
    body.content = checkin_view()
    page.add(body)


if __name__ == "__main__":
    ft.run(main)
