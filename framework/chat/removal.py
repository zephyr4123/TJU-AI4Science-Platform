"""删东西时目录外那部分的级联：对话在 CLI 那边的会话、工作区在每台机器上的镜像（主人 2026-09-22：
从根删干净）。workspace 层只删目录、用回调把这两样交上来；这里把回调接上 backends 与 computes，
终端（`ai4sci … remove`）与页面（`POST …/remove`）共用。

删不掉不吞也不拦：本机照删，没清干净的每条记成一句人话（哪段对话的会话、哪台机器的镜像、为什么），
调用方打给人、退出码非零。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from backends import BackendNotFound, Chat
from compute import ComputeError
from framework import computes
from framework.chat import conversation, scope
from framework.contracts.output import Meta
from framework.workspace import removal
from framework.workspace.project import Project
from framework.workspace.removal import RemovalRefused, Removed
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.removal")


def forget_chats(project: Project, chat_factory: Callable[[str], Chat]) -> list[str]:
    """项目里每段对话：还在一轮里就整个拒；让这家 CLI 忘掉那条会话，适配器不在或删不掉记一句。
    目录本身随项目一起删，这里不动。"""
    leftovers: list[str] = []
    for conv in conversation.list_conversations(project.chats):
        if conversation.busy(conv):
            raise RemovalRefused(f"对话 {conv.chat_id} 正有一轮在跑，等它结束再删")
        if not conv.session_id:
            continue
        try:
            chat_factory(conv.backend).forget(conv.session_id, Path(conv.cwd))
        except BackendNotFound as exc:
            leftovers.append(f"对话 {conv.chat_id} 在 {conv.backend} 那边的会话没清：{exc}")
        except OSError as exc:
            leftovers.append(f"对话 {conv.chat_id} 在 {conv.backend} 那边的会话没清：{exc}")
    return leftovers


def remove_mirrors(workspace: Workspace, metas: list[Meta]) -> list[str]:
    """产出在哪几台 ssh 机器上跑过，就去哪几台删这个工作区的镜像目录；机器不在清单里、连不上
    都记一句。"""
    leftovers: list[str] = []
    for name in removal.mirrors_of(metas):
        try:
            compute = computes.instance(name)
            compute.remove_dir(compute.remote_dir_for(workspace.root))
        except (computes.ComputesInvalid, KeyError, LookupError, ComputeError) as exc:
            leftovers.append(f"{name} 上的镜像没删：{exc}")
    return leftovers


def remove_project(project: Project, chat_factory: Callable[[str], Chat]) -> Removed:
    return removal.remove_project(
        project, forget_chats=lambda p: forget_chats(p, chat_factory),
        remove_mirrors=remove_mirrors)


def remove_workspace(workspace: Workspace) -> Removed:
    return removal.remove_workspace(workspace, remove_mirrors=remove_mirrors)


def remove_chat(where: scope.Scope, chat_id: str, chat_factory: Callable[[str], Chat]) -> Removed:
    """删一段对话：这家适配器不在就只删目录、记一句。"""
    conv = conversation.load_conversation(where.chats, chat_id)
    leftovers: list[str] = []
    chat: Chat | None
    try:
        chat = chat_factory(conv.backend)
    except BackendNotFound as exc:
        chat = None
        leftovers.append(f"{conv.backend} 那边的会话没清：{exc}")
    conversation.remove_conversation(conv, chat)
    return Removed(chat_id, leftovers)


__all__ = ["Removed", "RemovalRefused", "forget_chats", "remove_chat", "remove_mirrors",
           "remove_project", "remove_workspace"]
