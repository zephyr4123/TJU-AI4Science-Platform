"""作业跑完叫醒研究助理：以「框架」的身份给那段对话发一轮（外层 #63）。

在 chat 层：它认识对话与后端，不认识能力。调用方是 cli 层的作业子进程——作业记录里有 chat_id
（起 agent 时经 `AI4SCI_CHAT_ID` 传给它调用的命令，`--detach` 记下来），跑完就来这里。作业与对话
在同一个工作区里（P-15），所以拿着工作区就能找到该叫醒谁。
对话正忙（人正在说话）就隔一会儿再试；等不到、对话不在、后端不对，都把那句话记回作业记录，
不悄悄丢掉（P-7）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from backends import BackendNotFound, get_chat
from framework.chat import conversation, guide, scope, settings
from framework.workspace.jobs import Job
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.notify")
RETRY_S = 15.0
MAX_WAIT_S = 1800.0
ORIGIN = "框架"


def message_for(job: Job) -> str:
    """叫醒那一轮的话：作业是哪条命令、结果如何，然后把决定留给 agent。"""
    verdict = "跑完了，退出码 0" if job.exit_code == 0 else f"没跑成，退出码 {job.exit_code}"
    return (f"作业 {job.job_id}（`ai4sci {' '.join(job.argv)}`）{verdict}：\n{job.result}\n\n"
            "看一眼结果（ai4sci show output <id> / show job），用人话告诉研究者发生了什么、"
            "下一步打算怎么办；要调用下一条命令就调，长的照旧 --detach。")


def wake(workspace: Workspace, job: Job, *, retry_s: float = RETRY_S,
         max_wait_s: float = MAX_WAIT_S, sleep: Callable[[float], None] = time.sleep) -> str:
    """发一轮，返回一句状态：done / error: …（那一轮没走完）/ busy: …（等不到）/ failed: …。"""
    assert job.chat_id, "没有 chat_id 的作业不该来叫醒"
    where = scope.for_workspace(workspace)
    try:
        conv = settings.ensure_tuned(conversation.load_conversation(where.chats, job.chat_id))
        chat = get_chat(conv.backend)
        system_prompt = where.system_prompt(chat)
    except (conversation.ConversationNotFound, BackendNotFound, guide.GuideMissing) as exc:
        LOGGER.error("wake_failed job_id=%s chat_id=%s why=%s", job.job_id, job.chat_id, exc)
        return f"failed: {exc}"
    text = message_for(job)
    waited = 0.0
    while True:
        try:
            last = None
            for event in conversation.send(
                conv, chat, text, system_prompt=system_prompt,
                allowed_paths=list(where.allowed_paths), bash_rules=guide.BASH_RULES,
                readable_paths=list(where.readable_paths), origin=ORIGIN,
            ):
                last = event
        except conversation.ConversationBusy:
            if waited >= max_wait_s:
                LOGGER.error("wake_busy job_id=%s chat_id=%s waited_s=%.0f",
                             job.job_id, job.chat_id, waited)
                return f"busy: 等了 {waited:.0f} 秒对话一直在忙，没叫醒"
            sleep(retry_s)
            waited += retry_s
            continue
        status = "done" if last is not None and last.kind == "done" else (
            f"error: {last.text if last is not None else '适配器一个事件都没吐'}")
        LOGGER.info("wake_done job_id=%s chat_id=%s status=%s", job.job_id, job.chat_id, status)
        return status
