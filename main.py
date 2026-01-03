#!/usr/bin/env python3
import os
import asyncio
import random

from dotenv import load_dotenv
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Optional, Set

from telethon import TelegramClient, functions, types
from telethon.tl.types import User, Chat, Channel

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, Static, Input, Button
from textual.widgets._tree import TreeNode
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal


# ========= НАСТРОЙКИ TELEGRAM API =========

def create_env_file() -> None:
    """Создает .env файл, запрашивая ввод у пользователя."""
    env_path = ".env"
    
    if os.path.exists(env_path):
        return
    
    print("Файл .env не найден. Пожалуйста, введите настройки в следующем формате:")
    print("API_ID=aaaaaaa")
    print("API_HASH=aaaaaaa")
    print("SESSION_NAME=userbot_session")
    print("NTP_HOST=pool.ntp.org")
    print("\nВведите данные (можно вставить все строки сразу, завершите ввод пустой строкой):")
    
    lines = []
    while True:
        try:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        except (EOFError, KeyboardInterrupt):
            print("\nВвод прерван.")
            raise RuntimeError("Создание .env файла отменено.")
    
    if not lines:
        raise RuntimeError("Не введены данные для .env файла.")
    
    # Сохраняем введенные данные в .env файл
    with open(env_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    
    print(f"Файл .env создан.")


load_dotenv()

API_ID: int = int(os.getenv("API_ID", "0"))
API_HASH: str = os.getenv("API_HASH", "")
SESSION_NAME: str = os.getenv("SESSION_NAME", "userbot_session")

NTP_HOST: str = os.getenv("NTP_HOST", "pool.ntp.org")

# ========= МОДЕЛИ =========

@dataclass(frozen=True)
class DialogInfo:
    id: int
    title: str
    kind: str      # "private" | "group" | "channel" | "bot" | "unknown"
    is_forum: bool
    raw_entity: object


@dataclass(frozen=True)
class TopicInfo:
    id: int
    title: str
    unread_count: int = 0
    pinned: bool = False
    closed: bool = False


@dataclass(frozen=True)
class TopicNodeData:
    dialog: DialogInfo
    topic: TopicInfo


@dataclass(frozen=True)
class SendTarget:
    dialog: DialogInfo
    topic_id: Optional[int] = None
    topic_title: Optional[str] = None

    @property
    def label(self) -> str:
        if self.topic_id and self.topic_id != 1:
            return f"{self.dialog.title} / {self.topic_title or 'Тема'}"
        return self.dialog.title


@dataclass
class ScheduledJob:
    target: SendTarget
    text: str
    when: datetime


# ========= ЗАГРУЗКА ДИАЛОГОВ =========

async def load_dialogs(client: TelegramClient) -> List[DialogInfo]:
    dialogs: List[DialogInfo] = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = dialog.name or "Без названия"

        kind = "unknown"
        did = dialog.id
        is_forum = False

        if isinstance(entity, User):
            kind = "bot" if entity.bot else "private"
            did = entity.id

        elif isinstance(entity, Chat):
            kind = "group"
            did = entity.id

        elif isinstance(entity, Channel):
            if entity.megagroup:
                kind = "group"
                is_forum = bool(getattr(entity, "forum", False))
            else:
                kind = "channel"
            did = entity.id

        dialogs.append(
            DialogInfo(
                id=did,
                title=title,
                kind=kind,
                is_forum=is_forum,
                raw_entity=entity,
            )
        )

    return dialogs


# ========= ЗАГРУЗКА ТЕМ ФОРУМА =========

async def get_all_forum_topics(
    client: TelegramClient,
    peer: object,
    limit: int = 100,
) -> List[TopicInfo]:
    all_topics: List[TopicInfo] = []

    offset_date: Optional[datetime] = None
    offset_id = 0
    offset_topic = 0

    while True:
        res = await client(
            functions.messages.GetForumTopicsRequest(
                peer=peer,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=limit,
            )
        )

        topics = list(getattr(res, "topics", []) or [])
        if not topics:
            break

        for t in topics:
            title = getattr(t, "title", None)
            if not title:
                continue

            all_topics.append(
                TopicInfo(
                    id=int(getattr(t, "id", 0) or 0),
                    title=str(title),
                    unread_count=int(getattr(t, "unread_count", 0) or 0),
                    pinned=bool(getattr(t, "pinned", False)),
                    closed=bool(getattr(t, "closed", False)),
                )
            )

        if len(topics) < limit:
            break

        last = topics[-1]
        offset_topic = int(getattr(last, "id", 0) or 0)
        offset_id = int(getattr(last, "top_message", 0) or 0)

        last_msg_date: Optional[datetime] = None
        for m in getattr(res, "messages", []) or []:
            if getattr(m, "id", None) == offset_id:
                val = getattr(m, "date", None)
                if isinstance(val, datetime):
                    last_msg_date = val
                else:
                    last_msg_date = None
                break
        offset_date = last_msg_date

    all_topics.sort(key=lambda x: (not x.pinned, x.title.lower()))
    return all_topics


# ========= ВРЕМЯ / NTP =========

def parse_datetime(user_text: str) -> Optional[datetime]:
    """
    Поддерживаемые форматы:
    - HH:MM
    - HH:MM:SS
    - YYYY-MM-DD HH:MM
    - DD.MM.YYYY HH:MM
    Возвращает datetime или None, если формат не подходит.
    """
    s = user_text.strip()

    try:
        parts = s.split(":")
        if len(parts) == 2:  # HH:MM
            hh, mm = parts
            hh_i = int(hh)
            mm_i = int(mm)
            today = date.today()
            return datetime(today.year, today.month, today.day, hh_i, mm_i)

        elif len(parts) == 3 and " " not in s:  # HH:MM:SS (без даты)
            hh, mm, ss = parts
            hh_i = int(hh)
            mm_i = int(mm)
            ss_i = int(ss)
            today = date.today()
            return datetime(today.year, today.month, today.day, hh_i, mm_i, ss_i)

    except Exception:
        pass

    # Форматы с датой
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


async def get_time_delta_ntp(ntp_host: str) -> float:
    """
    Возвращает поправку времени (сек): ntp_time - local_time.
    Если ntplib не установлен или NTP недоступен, возвращает 0.
    """
    try:
        import ntplib  # type: ignore
    except Exception:
        return 0.0

    def _sync() -> float:
        c = ntplib.NTPClient()
        r = c.request(ntp_host, version=3, timeout=3)
        ntp_dt = datetime.fromtimestamp(r.tx_time)
        local_dt = datetime.now()
        return (ntp_dt - local_dt).total_seconds()

    try:
        return await asyncio.to_thread(_sync)
    except Exception:
        return 0.0


# ========= ОТПРАВКА С УЧЁТОМ ТЕМ =========

async def send_text_to_target(client: TelegramClient, target: SendTarget, text: str) -> None:
    """
    Если указана тема форума (topic_id != 1),
    отправляем сообщение в нужный топик через reply_to=topic_id.
    """
    if target.topic_id and target.topic_id != 1:
        # Для форумов: отправка в тему = reply к сообщению создания темы (topic id)
        await client.send_message(
            target.dialog.raw_entity,
            text,
            reply_to=target.topic_id,
        )
    else:
        await client.send_message(target.dialog.raw_entity, text)



# ========= UI: МОДАЛКА ТАЙМЕРА =========

class ScheduleScreen(ModalScreen):
    DEFAULT_CSS = """
    ScheduleScreen {
        align: center middle;
    }

    #dialog {
        width: 80%;
        max-width: 100;
        border: tall $panel;
        padding: 1 2;
        background: $surface;
    }

    Input {
        width: 1fr;
    }

    #buttons {
        height: auto;
        margin-top: 1;
        align: right middle;
    }

    Button {
        margin-left: 1;
    }
    """

    def __init__(self, target: SendTarget):
        super().__init__()
        self.target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"Цель: {self.target.label}")
            yield Static("Время отправки (HH:MM / HH:MM:SS / YYYY-MM-DD HH:MM / DD.MM.YYYY HH:MM)")
            yield Input(placeholder="Например: 23:45", id="when_input")
            yield Static("Текст сообщения")
            yield Input(placeholder="Текст...", id="text_input")
            with Horizontal(id="buttons"):
                yield Button("Отмена", id="cancel_btn")
                yield Button("Запланировать", id="ok_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.app.pop_screen()
            return

        if event.button.id == "ok_btn":
            when_str = self.query_one("#when_input", Input).value
            text = self.query_one("#text_input", Input).value

            self.app.pop_screen()
            self.app.schedule_message_from_ui(self.target, when_str, text)  # type: ignore


# ========= ОСНОВНОЕ TUI =========

class TelegramTui(App):
    CLEANUP_INTERVAL = 60

    CSS = """
    Screen {
        layout: vertical;
    }

    Tree {
        height: 1fr;
    }

    #status_bar {
        height: auto;
        padding: 0 1;
        background: $surface;
        border-top: solid $panel;
    }
    """

    BINDINGS = [
        ("q", "quit", "Выход"),
        ("r", "reload", "Обновить дерево"),
        ("t", "timer", "Запланировать сообщение"),
    ]

    def __init__(self, client: TelegramClient, dialogs: List[DialogInfo], time_delta_sec: float) -> None:
        super().__init__()
        self.client = client
        self.dialogs = dialogs
        self.time_delta_sec = time_delta_sec

        self.topics_loaded: Set[int] = set()
        self.current_target: Optional[SendTarget] = None

        self.jobs: List[ScheduledJob] = []
        self.job_tasks: List[asyncio.Task] = []
        self._cleanup_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tree("Диалоги", id="dialog_tree")
        yield Static("", id="status_bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the UI and start background tasks."""
        self.build_tree()
        delta_ms = int(self.time_delta_sec * 1000)
        self.set_status(
            f"Готово. Поправка времени (NTP): {delta_ms} мс. "
            "Выдели чат или тему и нажми t."
        )
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def on_shutdown(self) -> None:
        """Handle application shutdown."""
        # Cancel all running job tasks
        for task in self.job_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to complete or be cancelled
        if self.job_tasks:
            await asyncio.gather(*self.job_tasks, return_exceptions=True)
            
        # Cancel and wait for cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Периодически чистим списки от завершённых задач."""
        try:
            while True:
                await asyncio.sleep(self.CLEANUP_INTERVAL)
                
                # Clean up completed tasks
                active_tasks = []
                for task in self.job_tasks:
                    if task.done():
                        try:
                            await task  # This will raise any exceptions from the task
                        except Exception as e:
                            self.log.error(f"Error in background task: {e}")
                    else:
                        active_tasks.append(task)
                self.job_tasks = active_tasks
                
                # Clean up expired jobs
                now = self._corrected_now()
                self.jobs = [j for j in self.jobs if j.when > now]
                
        except asyncio.CancelledError:
            # Normal shutdown
            return
        except Exception as e:
            self.log.error(f"Error in cleanup loop: {e}")
            raise

    async def on_exit(self) -> None:
        await self.on_shutdown()

    def set_status(self, text: str) -> None:
        self.query_one("#status_bar", Static).update(text)

    # ---- дерево ----

    def build_tree(self) -> None:
        tree: Tree = self.query_one("#dialog_tree", Tree)
        tree.reset("Диалоги")

        root = tree.root
        node_private: TreeNode = root.add("Личные")
        node_groups: TreeNode = root.add("Группы")
        node_channels: TreeNode = root.add("Каналы / боты")

        for d in sorted(self.dialogs, key=lambda x: x.title.lower()):
            label = d.title

            if d.kind == "bot":
                label = f"🤖 {label}"

            if d.kind == "group":
                if d.is_forum:
                    label = f"{label}  • темы"
                    node_groups.add(label, data=d, allow_expand=True)
                else:
                    node_groups.add_leaf(label, data=d)

            elif d.kind == "private":
                node_private.add_leaf(label, data=d)

            elif d.kind == "channel":
                node_channels.add_leaf(label, data=d)

            elif d.kind == "bot":
                node_channels.add_leaf(label, data=d)

            else:
                root.add_leaf(f"(?) {label}", data=d)

        root.expand()
        node_private.expand()
        node_groups.expand()
        node_channels.expand()

    async def action_reload(self) -> None:
        self.topics_loaded.clear()
        self.current_target = None
        self.dialogs = await load_dialogs(self.client)
        self.build_tree()
        self.set_status("Диалоги и дерево обновлены.")


    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        data = event.node.data

        if isinstance(data, DialogInfo):
            if data.kind in ("private", "group", "channel", "bot"):
                self.current_target = SendTarget(dialog=data)
                self.set_status(f"Выбран чат: {data.title}")
            else:
                self.current_target = None

        elif isinstance(data, TopicNodeData):
            self.current_target = SendTarget(
                dialog=data.dialog,
                topic_id=data.topic.id,
                topic_title=data.topic.title,
            )
            self.set_status(f"Выбрана тема: {data.dialog.title} / {data.topic.title}")

        elif isinstance(data, TopicInfo):
            # На случай, если где-то остались старые узлы
            self.set_status("Выбрана тема (без контекста группы). Обнови дерево (r).")

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        data = node.data

        if not isinstance(data, DialogInfo):
            return
        if data.kind != "group" or not data.is_forum:
            return
        if data.id in self.topics_loaded:
            return

        self.topics_loaded.add(data.id)

        node.remove_children()
        loading = node.add_leaf("Загрузка тем...")

        try:
            topics = await get_all_forum_topics(self.client, data.raw_entity)
        except Exception:
            node.remove_children()
            node.add_leaf("Ошибка загрузки тем")
            return
        finally:
            try:
                loading.remove()
            except Exception:
                pass

        node.remove_children()

        if not topics:
            node.add_leaf("Тем нет")
            return

        for t in topics:
            flags = []
            if t.pinned:
                flags.append("📌")
            if t.closed:
                flags.append("🔒")
            if t.unread_count:
                flags.append(f"({t.unread_count})")

            suffix = (" " + " ".join(flags)) if flags else ""
            node.add_leaf(
                f"{t.title}{suffix}",
                data=TopicNodeData(dialog=data, topic=t)
            )

    # ---- таймер ----

    def action_timer(self) -> None:
        if not self.current_target:
            self.set_status("Выбери чат или тему в дереве, затем нажми t.")
            return

        self.push_screen(ScheduleScreen(self.current_target))

    def schedule_message_from_ui(self, target: SendTarget, when_str: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            self.set_status("Текст сообщения пустой.")
            return

        when = parse_datetime(when_str)
        if not when:
            self.set_status("Не понял формат времени.")
            return

        # If user entered time-only (HH:MM) or (HH:MM:SS) and it's not in the future versus corrected now,
        # roll it forward to the next day to avoid immediate send.
        corrected_now = self._corrected_now()
        is_time_only = (":" in when_str) and (" " not in when_str) and (len(when_str.strip()) <= 8)
        if is_time_only and when <= corrected_now:
            when = when + timedelta(days=1)

        job = ScheduledJob(target=target, text=text, when=when)
        self.jobs.append(job)

        task = asyncio.create_task(self._run_job(job))
        self.job_tasks.append(task)

        self.set_status(
            f"Запланировано: «{target.label}» на {when.strftime('%Y-%m-%d %H:%M:%S')}."
        )

    def _corrected_now(self) -> datetime:
        return datetime.now() + timedelta(seconds=self.time_delta_sec)

    async def _run_job(self, job: ScheduledJob) -> None:
        delay = (job.when - self._corrected_now()).total_seconds()

        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

        try:
            await send_text_to_target(self.client, job.target, job.text)
        except Exception as e:
            self.set_status(f"Ошибка отправки в «{job.target.label}»: {type(e).__name__}")
            return

        self.set_status(f"Сообщение отправлено в «{job.target.label}».")


# ========= ТОЧКА ВХОДА =========

async def main_async() -> None:
    # Создаем .env файл, если его нет
    create_env_file()
    
    # Перезагружаем переменные окружения после создания .env
    load_dotenv(override=True)
    
    # Получаем значения после создания .env
    api_id = int(os.getenv("API_ID", "0"))
    api_hash = os.getenv("API_HASH", "")
    session_name = os.getenv("SESSION_NAME", "userbot_session")
    ntp_host = os.getenv("NTP_HOST", "pool.ntp.org")
    
    if not api_id or not api_hash:
        raise RuntimeError("Заполни API_ID и API_HASH в .env.")

    client = TelegramClient(session_name, api_id, api_hash)

    await client.start()

    time_delta_sec = await get_time_delta_ntp(ntp_host)

    dialogs = await load_dialogs(client)

    app = TelegramTui(client, dialogs, time_delta_sec)

    async with client:
        await app.run_async()


if __name__ == "__main__":
    asyncio.run(main_async())
