"""作业跑完叫醒研究助理：结果先进那段对话的收件箱，然后尽量当场以「框架」的身份发一轮把收件箱念完
（外层 #63；#136 改收件箱）。

在 chat 层：它认识对话与后端，不认识能力。调用方是 cli 层的作业子进程——作业记录里有 chat_id
（起 agent 时经 `AI4SCI_CHAT_ID` 传给它调用的命令，`--detach` 记下来），跑完就来这里。作业在
工作区里、对话在项目里，拿着工作区找到项目就找到该叫醒谁。
对话正忙（人正在说话）就留在收件箱，正跑的那一轮结束后由它接着念（`follow_up`，服务与终端都在人那
一轮之后调）；这里只再试几秒——正跑的那一轮若恰好在收尾，几秒后就能拿到锁。原来是「忙就 15 秒重试、
30 分钟放弃」：一个项目几个工作区同时跑、都来敲同一段对话就会丢。对话不在、后端不对，都把那句话
记回作业记录，不悄悄丢掉（P-7）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator

from backends import BackendNotFound, Chat, ChatEvent, get_chat
from framework.chat import conversation, guide, scope, settings
from framework.workspace import project
from framework.workspace.jobs import Job
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.notify")
RETRY_S = 1.0
SETTLE_S = 10.0


def message_for(job: Job, workspace: Workspace) -> str:
    """叫醒那一轮的话：哪个工作区、作业是哪条命令、结果如何，然后把决定留给 agent。"""
    verdict = "跑完了，退出码 0" if job.exit_code == 0 else f"没跑成，退出码 {job.exit_code}"
    command = " ".join(job.argv)
    return (f"工作区 {workspace.id} 的作业 {job.job_id}（`ai4sci {command}`）{verdict}：\n"
            f"{job.result}\n\n"
            f"看一眼结果（ai4sci show output <id> --ws {workspace.id} / show job），"
            "用人话告诉研究者"
            "发生了什么、下一步打算怎么办；要调用下一条命令就调，长的照旧 --detach。")


def wake(workspace: Workspace, job: Job, *, settle_s: float = SETTLE_S,
         sleep: Callable[[float], None] = time.sleep) -> str:
    """作业跑完：结果排进收件箱，然后尽量当场念完。返回一句状态：done / queued（对话忙，留给它
    自己念）
    / error: …（那一轮没走完）/ failed: …（对话不在、后端不对，话没排进去）。"""
    assert job.chat_id, "没有 chat_id 的作业不该来叫醒"
    try:
        where = scope.for_project(project.of(workspace))
        conv = settings.ensure_tuned(conversation.load_conversation(where.chats, job.chat_id))
        chat = get_chat(conv.backend)
        system_prompt = where.system_prompt(chat)
    except (project.ProjectNotFound, conversation.ConversationNotFound, BackendNotFound,
            guide.GuideMissing) as exc:
        LOGGER.error("wake_failed job_id=%s chat_id=%s why=%s", job.job_id, job.chat_id, exc)
        return f"failed: {exc}"
    conversation.queue_note(conv, message_for(job, workspace))
    waited = 0.0
    while True:
        try:
            status = deliver(where, conv, chat, system_prompt)
        except conversation.ConversationBusy:
            if waited >= settle_s:
                LOGGER.info("wake_queued job_id=%s chat_id=%s", job.job_id, job.chat_id)
                return "queued"
            sleep(RETRY_S)
            waited += RETRY_S
            continue
        LOGGER.info("wake_done job_id=%s chat_id=%s status=%s", job.job_id, job.chat_id, status)
        return status


def deliver(where: scope.Scope, conv: conversation.Conversation, chat: Chat,
            system_prompt: str) -> str:
    """把收件箱念完（事件不往外吐，落盘就够）。返回 done，或那一轮没走完的 error: …；忙就抛。"""
    status = "done"
    for event in follow_up(where, conv, chat, system_prompt):
        if event.kind == "error":
            status = f"error: {event.text}"
    return status


def follow_up(where: scope.Scope, conv: conversation.Conversation, chat: Chat,
              system_prompt: str) -> Iterator[ChatEvent]:
    """收件箱不空就发一轮（框架），直到空；每轮的事件照样往外吐——服务与终端在人那一轮之后接着放。
    一轮没走完就停，别接着念（留在收件箱里的下次再说）。"""
    while True:
        seen = False
        for event in conversation.send_inbox(
            conv, chat, system_prompt=system_prompt, allowed_paths=list(where.allowed_paths),
            bash_rules=guide.bash_rules(where.kind), readable_paths=list(where.readable_paths),
        ):
            seen = True
            yield event
            if event.kind == "error":
                return
        if not seen:
            return
