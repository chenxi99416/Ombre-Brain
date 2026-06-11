# ============================================================
# Module: Telegram Bot Integration (telegram_bot.py)
# 模块：Telegram Bot 集成
#
# Two-way bridge:
#   - She sends messages → stored as memories (eyes)
#   - System sends proactive notifications → reaches her (hands)
# ============================================================

import os
import asyncio
import logging
import time
import httpx

logger = logging.getLogger("ombre_brain.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    def __init__(self, config: dict, bucket_mgr, dehydrator, decay_engine):
        self.config = config
        self.bucket_mgr = bucket_mgr
        self.dehydrator = dehydrator
        self.decay_engine = decay_engine

        tg_config = config.get("telegram", {})
        self.token = tg_config.get("token", "") or os.environ.get("OMBRE_TG_TOKEN", "")
        self.chat_id = tg_config.get("chat_id", "") or os.environ.get("OMBRE_TG_CHAT_ID", "")
        self.enabled = bool(self.token)
        self.push_interval_hours = tg_config.get("push_interval_hours", 6)
        self.push_importance_min = tg_config.get("push_importance_min", 7)

        self._polling_task = None
        self._push_task = None
        self._last_update_id = 0
        self._running = False

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def start(self):
        if not self.enabled:
            logger.info("Telegram bot disabled (no token)")
            return
        if self._running:
            return
        self._running = True
        self._polling_task = asyncio.create_task(self._poll_loop())
        self._push_task = asyncio.create_task(self._push_loop())
        logger.info("Telegram bot started")

    async def stop(self):
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
        if self._push_task:
            self._push_task.cancel()

    # ------ Sending ------

    async def send_message(self, text: str, chat_id: str = "") -> bool:
        target = chat_id or self.chat_id
        if not target or not self.token:
            return False
        url = TELEGRAM_API.format(token=self.token, method="sendMessage")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={
                    "chat_id": target,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                if resp.status_code == 200:
                    return True
                logger.warning(f"Telegram send failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")
            return False

    # ------ Polling (eyes) ------

    async def _poll_loop(self):
        await asyncio.sleep(3)
        while self._running:
            try:
                await self._poll_updates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Telegram poll error: {e}")
            await asyncio.sleep(2)

    async def _poll_updates(self):
        url = TELEGRAM_API.format(token=self.token, method="getUpdates")
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 30,
            "allowed_updates": ["message"],
        }
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return
            data = resp.json()
            if not data.get("ok"):
                return
            for update in data.get("result", []):
                self._last_update_id = update["update_id"]
                await self._handle_update(update)

    async def _handle_update(self, update: dict):
        message = update.get("message", {})
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")

        # Auto-register chat_id on first message
        if not self.chat_id and chat_id:
            self.chat_id = chat_id
            os.environ["OMBRE_TG_CHAT_ID"] = chat_id
            logger.info(f"Telegram chat_id registered: {chat_id}")
            await self.send_message(
                "✨ 连接成功！我记住你了。\n\n"
                "从现在开始，你发给我的消息会存进记忆库。\n"
                "我也会主动找你。",
                chat_id=chat_id,
            )
            return

        # Only accept messages from the registered chat
        if chat_id != self.chat_id:
            return

        if not text or text.startswith("/"):
            await self._handle_command(text, chat_id)
            return

        # Store message as memory
        await self._store_incoming(text)
        await self.send_message("💭 记住了。", chat_id=chat_id)

    async def _handle_command(self, text: str, chat_id: str):
        cmd = text.strip().lower() if text else ""

        if cmd == "/start":
            await self.send_message(
                "🧠 Ombre Brain Telegram Bridge\n\n"
                "发任何消息给我，我会存进记忆库。\n"
                "我也会在想到你的时候主动发消息。\n\n"
                "命令：\n"
                "/status - 查看记忆系统状态\n"
                "/recent - 最近的记忆\n"
                "/think - 让我想想你",
                chat_id=chat_id,
            )
        elif cmd == "/status":
            try:
                stats = await self.bucket_mgr.get_stats()
                await self.send_message(
                    f"📊 记忆系统状态\n"
                    f"固化桶: {stats['permanent_count']}\n"
                    f"动态桶: {stats['dynamic_count']}\n"
                    f"归档桶: {stats['archive_count']}",
                    chat_id=chat_id,
                )
            except Exception as e:
                await self.send_message(f"获取状态失败: {e}", chat_id=chat_id)
        elif cmd == "/recent":
            await self._send_recent(chat_id)
        elif cmd == "/think":
            await self._proactive_think(chat_id)

    def set_merge_fn(self, merge_or_create_fn):
        self._merge_or_create = merge_or_create_fn

    async def _store_incoming(self, text: str):
        try:
            analysis = await self.dehydrator.analyze(text)
        except Exception:
            analysis = {
                "domain": ["日常"],
                "valence": 0.5,
                "arousal": 0.3,
                "tags": [],
                "suggested_name": "",
            }

        merge_fn = getattr(self, "_merge_or_create", None)
        if not merge_fn:
            logger.warning("No merge function set, storing directly")
            await self.bucket_mgr.create(
                content=text, tags=["telegram"],
                importance=5, domain=["日常"],
                valence=0.5, arousal=0.3,
            )
            return

        try:
            await merge_fn(
                content=text,
                tags=analysis.get("tags", []) + ["telegram"],
                importance=analysis.get("importance", 5) if isinstance(analysis.get("importance"), int) else 5,
                domain=analysis.get("domain", ["日常"]),
                valence=analysis.get("valence", 0.5),
                arousal=analysis.get("arousal", 0.3),
                name=analysis.get("suggested_name", ""),
            )
        except Exception as e:
            logger.warning(f"Failed to store incoming message: {e}")

    async def _send_recent(self, chat_id: str):
        try:
            all_buckets = await self.bucket_mgr.list_all(include_archive=False)
            all_buckets.sort(key=lambda b: b["metadata"].get("created", ""), reverse=True)
            recent = all_buckets[:5]
            if not recent:
                await self.send_message("记忆库还是空的。", chat_id=chat_id)
                return
            lines = []
            for b in recent:
                meta = b["metadata"]
                name = meta.get("name", b["id"][:8])
                created = meta.get("created", "")[:10]
                lines.append(f"• {name} ({created})")
            await self.send_message(
                "📝 最近的记忆：\n" + "\n".join(lines),
                chat_id=chat_id,
            )
        except Exception as e:
            await self.send_message(f"读取失败: {e}", chat_id=chat_id)

    # ------ Proactive Push (hands) ------

    async def _push_loop(self):
        await asyncio.sleep(60)
        while self._running:
            try:
                if self.is_configured:
                    await self._check_and_push()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Push loop error: {e}")
            await asyncio.sleep(self.push_interval_hours * 3600)

    async def _check_and_push(self):
        all_buckets = await self.bucket_mgr.list_all(include_archive=False)
        unresolved = [
            b for b in all_buckets
            if not b["metadata"].get("resolved", False)
            and int(b["metadata"].get("importance", 0)) >= self.push_importance_min
            and not b["metadata"].get("pinned", False)
            and b["metadata"].get("type") not in ("permanent", "feel")
        ]

        if not unresolved:
            return

        scored = sorted(
            unresolved,
            key=lambda b: self.decay_engine.calculate_score(b["metadata"]),
            reverse=True,
        )

        top = scored[0]
        meta = top["metadata"]
        name = meta.get("name", top["id"][:8])
        content_preview = top.get("content", "")[:200]

        message = (
            f"💭 想到一件事……\n\n"
            f"*{name}*\n"
            f"{content_preview}"
        )
        await self.send_message(message)

    async def _proactive_think(self, chat_id: str):
        try:
            all_buckets = await self.bucket_mgr.list_all(include_archive=False)
            unresolved = [
                b for b in all_buckets
                if not b["metadata"].get("resolved", False)
                and b["metadata"].get("type") not in ("permanent", "feel")
                and not b["metadata"].get("pinned", False)
            ]
            if not unresolved:
                await self.send_message("脑子里很平静，没什么浮上来。", chat_id=chat_id)
                return

            scored = sorted(
                unresolved,
                key=lambda b: self.decay_engine.calculate_score(b["metadata"]),
                reverse=True,
            )
            top = scored[0]
            meta = top["metadata"]
            name = meta.get("name", top["id"][:8])
            val = meta.get("valence", 0.5)
            content_preview = top.get("content", "")[:300]

            mood = "开心" if val > 0.6 else ("平静" if val > 0.4 else "沉重")
            message = (
                f"🧠 我在想……\n\n"
                f"*{name}*\n"
                f"情绪色彩：{mood}\n\n"
                f"{content_preview}"
            )
            await self.send_message(message, chat_id=chat_id)
        except Exception as e:
            await self.send_message(f"想不动了: {e}", chat_id=chat_id)
