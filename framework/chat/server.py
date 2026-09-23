"""网页的后端：HTTP 端点包住 conversation.py 与 boards.py，事件用 SSE 推，页面本身也从这里端出去。

标准库 ThreadingHTTPServer：四十来个端点、单人本机服务，不值得引一个 web 框架。
零模型：模型在适配器的子进程里。
能力清单（`/cap`）、流程库（`/workflows`）、拼流程检查（`/workflows/check`）与描述符表（流程实例的进度要核对
点名的能力）由调用方以函数传入——这一层不认识 capabilities，依赖方向不能反过来。
页面是这些端点的客户端，换一种 UI 也是同一套（`ui/README.md`）。

端点按域分前缀（纲领 P-16）：项目 `/projects/<p>/…` 是研究助理的域（一个项目一位助理，外层 #136），
`/studio/…` 是流程助理的域，对话五个端点在两个前缀下共用一套实现；项目里的对话物理上到不了库。
工作区在项目之下：`/projects/<p>/workspaces/<id>/…`。

    GET  /health                            {"ok": true, "checks_ok":
    bool}（在用的底座与每台算力上次自检都过）
    GET  /backends                          每家 agent：产品名、模型清单、深度档位、
    新对话用的值（照设置）、
                                            哪家是「对话用」的缺省
    GET  /settings                          设置那一整份：底座（两层各用哪家、每家清单与缺省、
    上次检查）、算力、存放
    POST /settings/agents                   {"chat"?, "executor"?, "agents"?: {name: {model?,
    effort?}}} → 新的一整份
    POST /settings/check                    {"what"?: all|agents|computes|storage, "name"?} →
    真探并记回，带 ok / failed
    POST /settings/computes                 {"name", "ssh", "key", "root"?} 接一台机器（探测后记回）
    POST /settings/computes/<name>/remove   删一台
    GET  /stages                            七个研究阶段：名字与目录名，按清单顺序
    GET  /cap                               能力描述符清单：每个带 stage、五栏与 used_by
    GET  /skills                            能力库里 tag 为 skill 的：名字、一行、正文、脚本名
    GET  /workflows                         库：出厂的 `workflows/*.yaml` + 人存的
                                            `studio/workflows/*.yaml`，每条带 shipped 与
                                            covers / remarks / problems
    POST /workflows                         {name, title, summary, stages[, overwrite]}
                                            → 存进人存的那层（与出厂重名拒 409）
    POST /workflows/check                   同一个 body，只查不存：covers / remarks / problems
    POST /workflows/<name>/remove           删人存的一条流程（出厂的拒 403）
    GET  /templates                         需求模板的库：名字、标题、一句说明、原文
    GET  /projects                          项目清单：标题、几个工作区、有没有作业在跑
    POST /projects                          {"id", "title"?, "goal"?} → 新项目（写 project.md）
    GET  /projects/<p>                      项目 + 目标原文 + 每个工作区一行（需求状态、每个阶段几次
                                            产出、每条流程走到哪、在等谁、跑着的作业）
    POST /projects/<p>/remove               删整个项目（级联：工作区、对话及其会话、机器上的镜像）
    POST /projects/<p>/workspaces           {"id", "title"?, "template"?} → 项目里的新工作区
                                            （按模板起草 requirement.md）
    GET  /projects/<p>/workspaces/<id>      工作区 + 需求 + 七个阶段的产出 + 每条流程实例的进度
                                            + 作业（下面 …/ 都是这个前缀）
    POST …/workspaces/<id>/remove           删整个工作区（级联镜像；兄弟读过它的产出拒）
    GET  …/workspaces/<id>/requirement      需求：原文、按二级标题切的格、确认状态、上一版原文
    POST …/workspaces/<id>/requirement/confirm  {"by"} → 确认需求；人的确认，agent 不替人做
    GET  …/workspaces/<id>/flows            流程实例：covers / remarks / problems + 进度
    POST …/workspaces/<id>/flows/<name>/remove   删一条流程实例（挂着产出拒）
    GET  …/workspaces/<id>/outputs/<stage>/<n>  一次产出：记录、签字、文件清单（小文本带正文）、作业
    POST …/workspaces/<id>/outputs/<stage>/<n>/sign  {"by", "note"?} → 签字记录
    POST …/workspaces/<id>/outputs/<stage>/<n>/remove  删一次产出（只删叶子）
    GET  …/workspaces/<id>/files?path=<dir> 文件镜头：目录的一层（目录在前；.venv .git 不列），
                                            懒加载，path 空是工作区根
    GET  …/workspaces/<id>/file?path=<file> 一个文件：文本带正文（大的截断），二进制 text 为 null
    GET  …/workspaces/<id>/raw?path=<file>  文件原样端出（图片让浏览器显示）；出了工作区一律 422
    GET  …/workspaces/<id>/jobs[/<jid>]     作业清单 / 一个作业
    POST …/workspaces/<id>/jobs/<jid>/stop  {"by"} → 人叫停：杀进程树，作业记 stopped、产出记 failed
    GET  <域>/chats                         对话清单；<域> 是 /projects/<p> 或 /studio
    POST <域>/chats                         {"backend"?, "model"?, "effort"?} → 新对话的 meta
    GET  <域>/chats/<cid>                   meta + transcript + history
    POST <域>/chats/<cid>/messages          {"text", "model"?, "effort"?} → text/event-stream，
                                            一个事件一条；model / effort 给了就记进对话（没给
                                            沿用）；
                                            人这一轮说完，收件箱里排着的作业结果接着以「框架」的身份
                                            念，事件接在同一条流后面
    POST <域>/chats/<cid>/remove            删一段对话（连 CLI 那边的会话）
    GET  /<其它>                            `ui_dir` 里的静态文件，找不到的回 index.html（单页应用）
"""

from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Callable
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from backends import (
    TITLES,
    AgentProbe,
    BackendNotFound,
    Chat,
    ChatEvent,
    Tuning,
    available_backends,
    get_chat,
    probe,
)
from framework import agents, computes, paths
from framework.chat import boards, conversation, guide, notify, removal, scope, settings
from framework.contracts import output, requirement, stages, workflows
from framework.contracts.capability import Capability
from framework.workspace import jobs, outputs, project, root
from framework.workspace import removal as ws_removal

LOGGER = logging.getLogger("ai4sci.serve")
MAX_BODY = 1 << 20
# 这些是接口；其余 GET 路径都当页面的静态文件。加端点要在这里登记，不然会被当成页面路由。
API_ROOTS = ("health", "backends", "settings", "stages", "cap", "skills", "workflows", "templates",
             "projects", "studio")


def _no_add_compute(body: dict[str, Any]) -> dict[str, Any]:
    raise ValueError("这个服务没开「接机器」：在终端 ai4sci compute add")
INDEX_NAME = "index.html"


class ChatServer(ThreadingHTTPServer):
    """把运行参数挂在 server 上，handler 从 `self.server` 拿；不用全局变量。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, home: Path,
                 catalog: Callable[[], list[dict[str, Any]]],
                 skills: Callable[[], list[dict[str, Any]]] = lambda: [],
                 skill_names: Callable[[], frozenset[str]] = frozenset,
                 workflows: Callable[[], list[dict[str, Any]]],
                 stage_table: Callable[[], list[dict[str, Any]]] = stages.to_dicts,
                 check_workflow: Callable[[dict[str, Any]], dict[str, Any]],
                 save_workflow: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 descriptors: Callable[[], dict[str, Capability]] = dict,
                 chat_factory: Callable[[str], Chat] = get_chat,
                 add_compute: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 probe_agent: Callable[[str], AgentProbe] = probe,
                 system_prompts: dict[str, str] | None = None,
                 ui_dir: Path | None = None) -> None:
        super().__init__(address, Handler)
        self.home = Path(home).resolve()
        self.catalog = catalog
        self.skills = skills
        self.skill_names = skill_names
        self.workflows = workflows
        # 阶段表：cli 注入带主文件与它页面上的名字的那份（主文件表在 capabilities，chat 层不认识它）
        self.stage_table = stage_table
        self.check_workflow = check_workflow
        # 编辑台存流程：cli 注入（要对着能力清单核对，chat 层不认识 capabilities）；None 是不让存
        self.save_workflow = save_workflow
        # 能力描述符表：流程实例的进度要按它核对点名的能力；cli 注入，chat 层不认识 capabilities
        self.descriptors = descriptors
        self.chat_factory = chat_factory
        # 设置那块板要的清单与自检都跟着接的是哪家适配器走（测试里是剧本，不跑真 CLI）
        self.knobs_of = lambda name: chat_factory(name).knobs()
        self.probe_agent = probe_agent
        # 接一台机器：cli 注入（要就地探测，与 `ai4sci compute add` 同一段代码）；
        # None 是这个服务不开这功能
        self.add_compute = add_compute or _no_add_compute
        # 页面构建目录；None 就是没构建，根路径回一句怎么构建，接口照常
        self.ui_dir = None if ui_dir is None else Path(ui_dir).resolve()
        # 两份指南在起服务时各读一次：文件不在当场炸，不等第一条消息才发现。这里存的是不带
        # 「工具怎么用」的那份；发消息时按这段对话那家适配器补上它自己的那段（`system_prompt_for`）
        self.system_prompts = ({kind: guide.system_prompt(kind) for kind in guide.KINDS}
                               if system_prompts is None else system_prompts)
        self._injected_prompts = system_prompts is not None

    def system_prompt_for(self, kind: str, chat: Chat) -> str:
        """这个域的指南 + 这家 CLI 的「工具怎么用」。真指南由 guide 拼（那段插在前言之后）；
        测试注入的
        指南直接接在后面。"""
        tool = chat.tool_guide(guide.bash_rules(kind))
        if self._injected_prompts:
            base = self.system_prompts[kind]
            return base + ("\n\n" + tool.strip() + "\n" if tool.strip() else "")
        return guide.system_prompt(kind, tool_guide=tool)

    @property
    def projects_root(self) -> Path:
        return project.projects_root(self.home)


class Handler(BaseHTTPRequestHandler):
    server: ChatServer

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - 走 logging，不打 stderr
        LOGGER.info("http %s", fmt % args)

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        # 盘上的东西不合约（坏的 yaml、坏的报告、少了快照）是 422 一句话，不是掉线：连接一断
        # 页面只看得到「Failed to fetch」，什么都说不清（实测：flows/ 里一个只有一行的文件）
        try:
            self._get()
        except ValueError as exc:
            LOGGER.warning("http_get_unprocessable path=%s why=%s", self.path, exc)
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except OSError as exc:
            LOGGER.exception("http_get_failed path=%s", self.path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _get(self) -> None:
        url = urlsplit(self.path)
        parts = [p for p in url.path.split("/") if p]
        if not parts or parts[0] not in API_ROOTS:
            return self._static(url.path)
        if parts == ["health"]:
            # checks_ok：设置里在用的两家与每台算力上次自检都过了（没检查过也算过：不拦人）
            return self._json({"ok": True,
                               "checks_ok": not settings.problems(knobs=self.server.knobs_of,
                                                                  home=self.server.home)})
        if parts == ["backends"]:
            # 页面开新对话那一屏的三枚旋钮：哪家（缺省照设置里「对话用」的）、
            # 每家的清单与新对话用的值
            table = settings.agents_table(self.server.knobs_of)
            picked = {e["name"]: e for e in table["entries"]}
            rows = []
            for name in available_backends():
                knobs = asdict(self.server.chat_factory(name).knobs())
                entry = picked.get(name) or {}
                rows.append({"name": name, "title": TITLES.get(name, name),
                             "default": name == table["chat"], **knobs,
                             "model": entry.get("model", knobs["model"]),
                             "effort": entry.get("effort", knobs["effort"])})
            return self._json(rows)
        if parts == ["settings"]:
            return self._json(settings.snapshot(self.server.knobs_of, self.server.home))
        if parts == ["stages"]:
            return self._json(self.server.stage_table())
        if parts == ["cap"]:
            return self._json(self.server.catalog())
        if parts == ["skills"]:
            return self._json(self.server.skills())
        if parts == ["workflows"]:
            return self._json(self.server.workflows())
        if parts == ["templates"]:
            return self._json(boards.list_templates(paths.templates_root()))
        if parts == ["projects"]:
            return self._json([boards.project_summary(p) for p in
                               project.list_projects(self.server.projects_root)])
        found = self._scope(parts)
        if found is None:
            return None
        where, ws, rest = found
        if rest[:1] == ["chats"]:
            if ws is not None:
                return self._error(HTTPStatus.NOT_FOUND, "对话归项目：/projects/<p>/chats")
            return self._get_chat(where, rest[1:])
        if ws is None:
            if where.project is not None and rest == []:
                return self._json(boards.project_detail(where.project, self.server.descriptors(),
                                                        self.server.skill_names()))
            return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{url.path}")
        if rest == []:
            return self._json(self._detail(ws))
        if rest == ["requirement"]:
            return self._json(boards.requirement_detail(ws))
        if rest == ["flows"]:
            return self._json(self._detail(ws)["flows"])
        if len(rest) == 3 and rest[0] == "outputs":
            try:
                return self._json(boards.output_detail(ws, f"{rest[1]}/{rest[2]}"))
            except (ValueError, output.OutputNotFound) as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
        if rest in (["files"], ["file"], ["raw"]):
            return self._get_file(ws, rest[0], parse_qs(url.query).get("path", [""])[0])
        if rest == ["jobs"]:
            return self._json([job.to_dict() for job in jobs.list_jobs(ws.jobs)])
        if len(rest) == 2 and rest[0] == "jobs":
            try:
                return self._json(jobs.load(ws.jobs, rest[1]).to_dict())
            except jobs.JobNotFound as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{url.path}")

    def _get_file(self, ws: root.Workspace, what: str, rel: str) -> None:
        """文件镜头的三个只读端点。不在的路径 404；出了工作区的是 ValueError，外层回 422。"""
        try:
            if what == "files":
                return self._json(boards.list_dir(ws, rel))
            if what == "file":
                return self._json(boards.read_file(ws, rel))
            data, ctype = boards.raw_file(ws, rel)
        except FileNotFoundError as exc:
            return self._error(HTTPStatus.NOT_FOUND, str(exc))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'inline; filename="{Path(rel).name}"')
        self.end_headers()
        self.wfile.write(data)

    def _get_chat(self, where: scope.Scope, rest: list[str]) -> None:
        if rest == []:
            return self._json([{**c.to_dict(), "title": conversation.title(c)} for c in
                               conversation.list_conversations(where.chats)])
        if len(rest) == 1:
            conv = self._conversation(where, rest[0])
            if conv is None:
                return None
            transcript = (conv.dir / conversation.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            return self._json({**conv.to_dict(), "title": conversation.title(conv),
                               "transcript": transcript,
                               "history": conversation.read_turns(conv)})
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        self.streaming = False  # 头已经发出去（SSE）之后再出错，只能断流，不能再回一个 JSON
        try:
            self._post()
        except ValueError as exc:
            LOGGER.warning("http_post_unprocessable path=%s why=%s", self.path, exc)
            if self.streaming:
                raise
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except OSError as exc:
            LOGGER.exception("http_post_failed path=%s", self.path)
            if self.streaming:
                raise
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _post(self) -> None:
        parts = [p for p in urlsplit(self.path).path.split("/") if p]
        body = self._body()
        if body is None:
            return None
        if parts == ["workflows", "check"]:
            return self._json(self.server.check_workflow(body))
        if parts[:1] == ["settings"]:
            return self._post_settings(parts[1:], body)
        if len(parts) == 3 and parts[0] == "workflows" and parts[2] == "remove":
            try:
                workflows.Library(paths.workflows_root(),
                                  paths.user_workflows_root(self.server.home)).remove(parts[1])
            except FileNotFoundError as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
            except workflows.WorkflowInvalid as exc:  # 出厂的
                return self._error(HTTPStatus.FORBIDDEN, str(exc))
            return self._json({"removed": parts[1], "leftovers": []})
        if parts == ["workflows"]:
            if self.server.save_workflow is None:
                return self._error(HTTPStatus.NOT_IMPLEMENTED, "这个服务没开存流程")
            try:
                return self._json(self.server.save_workflow(body), HTTPStatus.CREATED)
            except ValueError as exc:  # WorkflowInvalid 继承 ValueError：形状不对、不通
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            except FileExistsError as exc:
                return self._error(HTTPStatus.CONFLICT, str(exc))
        if parts == ["projects"]:
            project_id = body.get("id")
            if not isinstance(project_id, str) or not project_id.strip():
                return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 id：项目名")
            try:
                made = project.create(self.server.projects_root, project_id.strip(),
                                      title=str(body.get("title") or ""),
                                      goal=str(body.get("goal") or ""))
            except project.ProjectInvalid as exc:
                status = HTTPStatus.CONFLICT if "已经有" in str(exc) else HTTPStatus.BAD_REQUEST
                return self._error(status, str(exc))
            return self._json(boards.project_summary(made), HTTPStatus.CREATED)
        found = self._scope(parts)
        if found is None:
            return None
        where, ws, rest = found
        if ws is not None and rest[:1] == ["chats"]:
            return self._error(HTTPStatus.NOT_FOUND, "对话归项目：/projects/<p>/chats")
        if ws is None and where.project is not None and rest == ["workspaces"]:
            return self._post_workspace(where.project, body)
        if rest[-1:] == ["remove"]:
            return self._post_remove(where, ws, rest[:-1])
        if rest == ["chats"]:
            try:
                knobs = self.server.knobs_of
                backend = str(body.get("backend") or agents.role_backend("chat", knobs))
                chat = self.server.chat_factory(backend)  # 名字不对现在就报，别等发消息
                # 新对话从按人的设置抄具体值（P-25），body 里给的压过它；剧本后端不在设置里就用起点
                start = (agents.tuning_for(backend, knobs) if backend in available_backends()
                         else chat.knobs().fill(None))
            except (BackendNotFound, agents.AgentsInvalid) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            tuning = self._tuning(body, start, chat)
            if tuning is None:
                return None
            conv = conversation.new_conversation(where.chats, backend, where.cwd, tuning=tuning)
            return self._json(conv.to_dict(), HTTPStatus.CREATED)
        if len(rest) == 3 and rest[0] == "chats" and rest[2] == "messages":
            conv = self._conversation(where, rest[1])
            if conv is None:
                return None
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 text")
            try:
                chat = self.server.chat_factory(conv.backend)
            except BackendNotFound as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            tuning = self._tuning(body, conv.tuning, chat)
            if tuning is None:
                return None
            return self._stream(where, conv, chat, text, tuning)
        if ws is None:
            return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")
        if rest == ["requirement", "confirm"]:
            by = self._by(body)
            if by is None:
                return None
            try:
                requirement.confirm(ws.root, by=by)
            except requirement.ConfirmRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.requirement_detail(ws), HTTPStatus.CREATED)
        if len(rest) == 4 and rest[0] == "outputs" and rest[3] == "sign":
            oid = f"{rest[1]}/{rest[2]}"
            try:
                directory, _ = outputs.find_output(ws, oid)
            except (ValueError, output.OutputNotFound) as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
            by = self._by(body)
            if by is None:
                return None
            try:
                output.sign(directory, by=by, note=str(body.get("note") or ""))
            except output.SignRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.output_detail(ws, oid), HTTPStatus.CREATED)
        if len(rest) == 3 and rest[0] == "jobs" and rest[2] == "stop":
            by = self._by(body)
            if by is None:
                return None
            try:
                job = jobs.stop(ws, rest[1], by=by)
            except jobs.JobNotFound as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
            except (jobs.JobNotRunning, output.OutputNotFound) as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(job.to_dict(), HTTPStatus.CREATED)
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── 内部 ─────────────────────────────────────────────────────────────
    def _scope(self, parts: list[str]
               ) -> tuple[scope.Scope, root.Workspace | None, list[str]] | None:
        """路径前缀定域：`/studio/…` 是编辑台，`/projects/<p>/…` 是那个项目，再往下
        `workspaces/<id>/…` 是项目里的那个工作区；剩下的路径交回去。

        项目与工作区只按名字从清单目录下取，不拿 URL 片段拼路径：`..` 之类先被名字规矩拒掉。"""
        if parts[0] == "studio":
            return scope.studio(self.server.home), None, parts[1:]
        if parts[0] == "projects" and len(parts) >= 2:
            project_id = parts[1]
            if not root.ID_RE.fullmatch(project_id):
                self._error(HTTPStatus.NOT_FOUND, f"没有这个项目：{project_id}")
                return None
            try:
                found = project.load(self.server.projects_root / project_id)
            except project.ProjectNotFound:
                self._error(HTTPStatus.NOT_FOUND, f"没有这个项目：{project_id}")
                return None
            where = scope.for_project(found)
            rest = parts[2:]
            if rest[:1] == ["workspaces"] and len(rest) >= 2:
                try:
                    ws = found.workspace(rest[1])
                except (root.WorkspaceInvalid, root.WorkspaceNotFound):
                    self._error(HTTPStatus.NOT_FOUND, f"项目 {project_id} 里没有工作区：{rest[1]}")
                    return None
                return where, ws, rest[2:]
            return where, None, rest
        self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")
        return None

    def _post_workspace(self, found: project.Project, body: dict[str, Any]) -> None:
        """项目里起一个工作区：按模板起草 requirement.md。"""
        ws_id = body.get("id")
        if not isinstance(ws_id, str) or not ws_id.strip():
            return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 id：工作区名")
        template_name = str(body.get("template") or "generic")
        template_path = paths.templates_root() / f"{template_name}.md"
        if not template_path.is_file():
            return self._error(HTTPStatus.BAD_REQUEST, f"库里没有叫 {template_name!r} 的需求模板")
        try:
            ws = project.new_workspace(found, ws_id.strip(), title=str(body.get("title") or ""),
                                       template=template_path.read_text(encoding="utf-8"))
        except root.WorkspaceInvalid as exc:
            status = HTTPStatus.CONFLICT if "已经有" in str(exc) else HTTPStatus.BAD_REQUEST
            return self._error(status, str(exc))
        return self._json(boards.workspace_summary(ws), HTTPStatus.CREATED)

    def _tuning(self, body: dict[str, Any], current: Tuning, chat: Chat) -> Tuning | None:
        """body 里的 model / effort：没给或 null 的键沿用 current（旋钮上只有具体值，没有「回缺省」
        ）；
        不是字符串或不在这家后端的清单上就 400。"""
        picked: dict[str, str | None] = {}
        for key in ("model", "effort"):
            value = body.get(key)
            if value is None:
                value = getattr(current, key)
            if value is not None and not isinstance(value, str):
                self._error(HTTPStatus.BAD_REQUEST, f"{key} 要是字符串")
                return None
            picked[key] = value
        tuning = Tuning(**picked)
        try:
            chat.knobs().check(tuning)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return None
        return tuning

    def _stream(self, where: scope.Scope, conv: conversation.Conversation, chat: Chat,
                text: str, tuning: Tuning) -> None:
        system_prompt = self.server.system_prompt_for(where.kind, chat)
        try:
            events = conversation.send(
                conv, chat, text, system_prompt=system_prompt,
                allowed_paths=list(where.allowed_paths), bash_rules=guide.bash_rules(where.kind),
                readable_paths=list(where.readable_paths), tuning=tuning)
            first = next(events)  # 忙、空消息这类错误在头响应之前就要报出来
        except conversation.ConversationBusy as exc:
            return self._error(HTTPStatus.CONFLICT, str(exc))
        except ValueError as exc:  # 空消息、搬家前的旧对话（ConversationStale）
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except StopIteration:
            return self._error(HTTPStatus.BAD_GATEWAY, "适配器一个事件都没吐")
        self.streaming = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._sse(first)
        for event in events:
            self._sse(event)
        # 人这一轮说着话时跑完的作业排在收件箱里：接着以「框架」的身份念，事件接在同一条流后面
        for event in notify.follow_up(where, conv, chat, system_prompt):
            self._sse(event)

    def _post_settings(self, rest: list[str], body: dict[str, Any]) -> None:
        """设置那块板的四个动作，都落到 chat/settings 与两份清单的读写点。"""
        try:
            if rest == ["agents"]:
                return self._json(settings.update_agents(body, self.server.knobs_of,
                                                         self.server.home))
            if rest == ["check"]:
                what = str(body.get("what") or "all")
                name = body.get("name")
                if what not in settings.WHATS or (name is not None and not isinstance(name, str)):
                    return self._error(HTTPStatus.BAD_REQUEST,
                                       f"what 只认 {settings.WHATS}，name 要是字符串")
                return self._json(settings.check(what, name, knobs=self.server.knobs_of,
                                                 probe_agent=self.server.probe_agent,
                                                 home=self.server.home))
            if rest == ["computes"]:
                return self._json(self.server.add_compute(body), HTTPStatus.CREATED)
            if len(rest) == 3 and rest[0] == "computes" and rest[2] == "remove":
                computes.remove(rest[1])
                return self._json(settings.snapshot(self.server.knobs_of, self.server.home))
        except ValueError as exc:
            # 名字不对（BackendNotFound / ComputeNotFound）、清单不合形状、值不在清单上：都是配置值
            # 非法
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    def _sse(self, event: ChatEvent) -> None:
        data = json.dumps(conversation.event_payload(event), ensure_ascii=False)
        self.wfile.write(f"event: {event.kind}\ndata: {data}\n\n".encode())
        self.wfile.flush()

    def _static(self, path: str) -> None:
        """页面的静态文件。找不到的路径回 index.html（单页应用自己认路由）；`assets/` 带哈希，
        可以长缓存。"""
        ui_dir = self.server.ui_dir
        if ui_dir is None:
            return self._error(HTTPStatus.NOT_FOUND,
                               "页面没构建：在 ui/web 里 npm run build（或 make ui），"
                               "也可以 ai4sci serve --ui <构建目录>")
        target = (ui_dir / path.lstrip("/")).resolve()
        if not target.is_relative_to(ui_dir):
            return self._error(HTTPStatus.FORBIDDEN, "路径越出页面目录")
        if target.is_dir():
            target = target / INDEX_NAME
        if not target.is_file():
            target = ui_dir / INDEX_NAME
            if not target.is_file():
                return self._error(HTTPStatus.NOT_FOUND, f"页面目录里没有 {INDEX_NAME}：{ui_dir}")
        data = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable"
                         if target.parent.name == "assets" else "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _post_remove(self, where: scope.Scope, ws: root.Workspace | None, what: list[str]) -> None:
        """删：对话（两个域都有）、整个项目、整个工作区、产出、流程实例。拒是 409，没有是 404；
        目录外没清干净的随 `leftovers` 回去，本机那部分已经删了。"""
        try:
            if what[:1] == ["chats"] and len(what) == 2:
                removed = removal.remove_chat(where, what[1], self.server.chat_factory)
            elif ws is None and where.project is not None and what == []:
                removed = removal.remove_project(where.project, self.server.chat_factory)
            elif ws is None:
                return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")
            elif what == []:
                removed = removal.remove_workspace(ws)
            elif what[:1] == ["outputs"] and len(what) == 3:
                removed = ws_removal.remove_output(ws, f"{what[1]}/{what[2]}")
            elif what[:1] == ["flows"] and len(what) == 2:
                removed = ws_removal.remove_flow(ws, what[1])
            else:
                return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")
        except (ws_removal.RemovalRefused, conversation.ConversationBusy) as exc:
            return self._error(HTTPStatus.CONFLICT, str(exc))
        except (conversation.ConversationNotFound, output.OutputNotFound, FileNotFoundError) as exc:
            return self._error(HTTPStatus.NOT_FOUND, str(exc))
        return self._json({"removed": removed.what, "leftovers": removed.leftovers})

    def _conversation(self, where: scope.Scope, chat_id: str) -> conversation.Conversation | None:
        try:
            # 老对话 meta 里的 null 读到时填成当时的缺省（P-25 之后旋钮上只有具体值）
            return settings.ensure_tuned(conversation.load_conversation(where.chats, chat_id),
                                         self.server.knobs_of)
        except conversation.ConversationNotFound as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
            return None
        except agents.AgentsInvalid as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return None

    def _by(self, body: dict[str, Any]) -> str | None:
        by = body.get("by")
        if not isinstance(by, str) or not by.strip():
            self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 by：谁确认的，记在记录上")
            return None
        return by.strip()

    def _body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body 太大")
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, f"body 不是合法 JSON：{exc}")
            return None
        if not isinstance(body, dict):
            self._error(HTTPStatus.BAD_REQUEST, "body 要是 JSON 对象")
            return None
        return body

    def _detail(self, ws):
        """工作区页那一整份：流程实例的格子上步骤与 skill 都要认。"""
        return boards.workspace_detail(ws, self.server.descriptors(), self.server.skill_names())

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(boards.jsonable(payload), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)
